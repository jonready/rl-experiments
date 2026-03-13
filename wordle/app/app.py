"""Flask app: play Wordle against the RL model at different training checkpoints."""

import os
import re
import sys

import boto3
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from openai import OpenAI

from inference import DevboxInference
from wordle import WordleGame, new_game

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

app = Flask(__name__)

# In-memory game store
games: dict[str, WordleGame] = {}

# Inference manager (lazy init)
_inference: DevboxInference | None = None


def get_inference() -> DevboxInference:
    global _inference
    if _inference is None:
        _inference = DevboxInference()
    return _inference


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url="https://0bbaac9c9052f0808f4187461bdefbfc.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_PRIMEINT_ACCESSKEYID"],
        aws_secret_access_key=os.environ["R2_PRIMEINT_SECRETACCESSKEY"],
    )


SYSTEM_PROMPT = """You are playing Wordle. You must guess a secret 5-letter English word in 6 tries.
After each guess, you receive feedback:
- 🟩 (correct): the letter is in the correct position
- 🟨 (present): the letter is in the word but in the wrong position
- ⬛ (absent): the letter is not in the word

Think carefully about which word to guess based on the feedback. Reply with ONLY a single 5-letter word as your guess."""


def build_messages(game: WordleGame) -> list[dict]:
    """Build chat messages from game history for the model."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if not game.guesses:
        messages.append({"role": "user", "content": "Please make your first guess."})
    else:
        for i, (guess, fb) in enumerate(zip(game.guesses, game.feedback)):
            # Model's guess
            messages.append({"role": "assistant", "content": guess})
            # Feedback
            feedback_str = ""
            for r in fb:
                letter = r["letter"].upper()
                if r["status"] == "correct":
                    feedback_str += f"🟩{letter} "
                elif r["status"] == "present":
                    feedback_str += f"🟨{letter} "
                else:
                    feedback_str += f"⬛{letter} "
            messages.append({
                "role": "user",
                "content": f"Turn {i+1} result: {feedback_str.strip()}\nMake your next guess.",
            })

    return messages


def parse_guess(response_text: str) -> str | None:
    """Extract a 5-letter word from model response, stripping <think> tags."""
    # Remove think blocks
    text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL)
    text = text.strip()

    # Look for a 5-letter word
    match = re.search(r"\b([a-zA-Z]{5})\b", text)
    if match:
        return match.group(1).lower()
    return None


# --- Routes ---


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/checkpoints")
def list_checkpoints():
    """List available checkpoints from R2."""
    try:
        s3 = get_r2_client()
        response = s3.list_objects_v2(
            Bucket="primeintellectmodels", Prefix="wordle/rl/step_", Delimiter="/"
        )
        steps = []
        for prefix in response.get("CommonPrefixes", []):
            p = prefix["Prefix"]  # e.g. "wordle/rl/step_10/"
            step_name = p.rstrip("/").split("/")[-1]  # "step_10"
            step_num = int(step_name.replace("step_", ""))
            steps.append({"name": step_name, "step": step_num})
        steps.sort(key=lambda x: x["step"])

        # Check for SFT model
        sft_resp = s3.list_objects_v2(
            Bucket="primeintellectmodels", Prefix="wordle/sft/final/", MaxKeys=1
        )
        has_sft = sft_resp.get("KeyCount", 0) > 0

        return jsonify({"checkpoints": steps, "has_sft": has_sft})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/checkpoint/switch", methods=["POST"])
def switch_checkpoint():
    """Download checkpoint to devbox and restart inference server."""
    data = request.json
    step = data.get("step", "sft")
    try:
        inf = get_inference()
        result = inf.switch_checkpoint(step)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/checkpoint/status")
def checkpoint_status():
    """Current checkpoint + server readiness."""
    try:
        inf = get_inference()
        return jsonify(inf.get_status())
    except Exception as e:
        return jsonify({"error": str(e), "running": False}), 500


@app.route("/api/game/new", methods=["POST"])
def new_game_route():
    """Start a new game."""
    game = new_game()
    games[game.game_id] = game
    return jsonify(game.to_dict())


@app.route("/api/game/turn", methods=["POST"])
def game_turn():
    """Model makes one guess."""
    data = request.json
    game_id = data.get("game_id")
    game = games.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404
    if game.finished:
        return jsonify({"error": "Game is finished", **game.to_dict()}), 400

    # Build messages and call model
    messages = build_messages(game)
    try:
        client = OpenAI(
            base_url="http://localhost:8000/v1",
            api_key="not-needed",
        )
        completion = client.chat.completions.create(
            model="default",
            messages=messages,
            max_tokens=1024,
            temperature=0.6,
        )
        raw_response = completion.choices[0].message.content
    except Exception as e:
        return jsonify({"error": f"Inference error: {e}"}), 500

    # Parse guess
    guess = parse_guess(raw_response)
    if not guess:
        return jsonify({
            "error": "Could not parse a 5-letter word from model response",
            "raw_response": raw_response,
            **game.to_dict(),
        }), 400

    # Make the guess
    feedback = game.make_guess(guess)

    return jsonify({
        **game.to_dict(),
        "last_guess": guess,
        "last_feedback": feedback,
        "raw_response": raw_response,
    })


@app.route("/api/metrics")
def metrics():
    """Return training metrics from R2 if available."""
    try:
        s3 = get_r2_client()
        obj = s3.get_object(Bucket="primeintellectmodels", Key="wordle/metrics.json")
        import json

        data = json.loads(obj["Body"].read().decode())
        return jsonify(data)
    except Exception:
        return jsonify({"steps": [], "rewards": [], "win_rates": []})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
