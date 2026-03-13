"""Wordle game logic: word list, guess evaluation, game state."""

import random
import uuid
from dataclasses import dataclass, field

# Standard Wordle answer list (2309 words) - curated subset
# Using the most common 200 for a playable demo; extend as needed
WORD_LIST = [
    "about", "above", "abuse", "actor", "acute", "admit", "adopt", "adult",
    "after", "again", "agent", "agree", "ahead", "alarm", "album", "alert",
    "alien", "align", "alive", "alley", "allow", "alone", "along", "alter",
    "among", "angel", "anger", "angle", "angry", "anime", "ankle", "annex",
    "apart", "apple", "apply", "arena", "argue", "arise", "armor", "array",
    "aside", "asset", "atlas", "audio", "audit", "avoid", "award", "aware",
    "badge", "badly", "baker", "basic", "basin", "basis", "batch", "beach",
    "beard", "beast", "begin", "being", "below", "bench", "berry", "birth",
    "black", "blade", "blame", "bland", "blank", "blast", "blaze", "bleed",
    "blend", "bless", "blind", "block", "blood", "bloom", "blown", "board",
    "boost", "bound", "brain", "brand", "brave", "bread", "break", "breed",
    "brick", "bride", "brief", "bring", "broad", "broke", "brook", "brown",
    "brush", "build", "built", "bunch", "burst", "buyer", "cabin", "cable",
    "camel", "candy", "cargo", "carry", "catch", "cause", "cedar", "chain",
    "chair", "chalk", "chaos", "charm", "chart", "chase", "cheap", "check",
    "cheek", "cheer", "chess", "chest", "chief", "child", "china", "chunk",
    "churn", "civic", "civil", "claim", "clash", "class", "clean", "clear",
    "clerk", "click", "cliff", "climb", "cling", "clock", "clone", "close",
    "cloud", "coach", "coast", "color", "comet", "comic", "coral", "couch",
    "could", "count", "court", "cover", "crack", "craft", "crane", "crash",
    "crawl", "crazy", "cream", "creek", "crews", "crime", "cross", "crowd",
    "crown", "crude", "crush", "cubic", "curve", "cycle", "daily", "dance",
    "dated", "dealt", "debug", "decay", "delay", "delta", "dense", "depot",
    "depth", "derby", "deter", "devil", "diary", "dirty", "dodge", "doing",
    "donor", "doubt", "dough", "draft", "drain", "drake", "drama", "drank",
    "drawn", "dream", "dress", "dried", "drift", "drill", "drink", "drive",
    "drone", "drops", "drove", "drugs", "drums", "drunk", "dryer", "dusty",
    "dying", "eager", "early", "earth", "eight", "elder", "elect", "elite",
    "embed", "empty", "enemy", "enjoy", "enter", "entry", "equal", "error",
    "essay", "ethos", "event", "every", "exact", "exams", "exile", "exist",
    "extra", "fable", "facet", "faint", "fairy", "faith", "false", "fancy",
    "fatal", "fault", "feast", "fence", "ferry", "fetch", "fever", "fiber",
    "field", "fifth", "fifty", "fight", "final", "first", "fixed", "flame",
    "flash", "fleet", "flesh", "flies", "float", "flood", "floor", "flour",
    "fluid", "flush", "focal", "focus", "force", "forge", "forth", "forum",
    "found", "frame", "frank", "fraud", "fresh", "front", "frost", "froze",
    "fruit", "fully", "funny", "giant", "given", "glass", "globe", "gloom",
    "glory", "gloss", "glove", "going", "grace", "grade", "grain", "grand",
    "grant", "grape", "graph", "grasp", "grass", "grave", "great", "greed",
    "green", "greet", "grief", "grill", "grind", "groan", "groom", "gross",
    "group", "grove", "grown", "guard", "guess", "guest", "guide", "guild",
    "guilt", "guise", "habit", "happy", "harsh", "hasty", "haunt", "haven",
    "heart", "heavy", "hedge", "herbs", "hobby", "honor", "horse", "hotel",
    "house", "human", "humid", "humor", "hurry", "hyper", "ideal", "image",
    "imply", "index", "indie", "inner", "input", "irony", "issue", "ivory",
    "jewel", "joint", "joker", "judge", "juice", "juicy", "jumbo", "kebab",
    "knack", "kneel", "knife", "knock", "known", "label", "lance", "large",
    "laser", "later", "laugh", "layer", "learn", "lease", "leave", "legal",
    "lemon", "level", "light", "limit", "linen", "liver", "lobby", "local",
    "logic", "login", "loose", "lover", "lower", "loyal", "lucky", "lunar",
    "lunch", "magic", "major", "maker", "manor", "maple", "march", "marry",
    "match", "maybe", "mayor", "media", "mercy", "merge", "merit", "metal",
    "meter", "might", "minor", "minus", "mirth", "model", "money", "month",
    "moral", "motor", "mount", "mouse", "mouth", "moved", "movie", "music",
    "naive", "named", "nasty", "naval", "nerve", "never", "night", "noble",
    "noise", "north", "noted", "novel", "nurse", "nylon", "occur", "ocean",
    "offer", "often", "olive", "omega", "onset", "opera", "orbit", "order",
    "organ", "other", "outer", "owned", "owner", "oxide", "ozone", "paint",
    "panel", "panic", "paper", "party", "pasta", "patch", "pause", "peace",
    "peach", "pearl", "penny", "phase", "phone", "photo", "piano", "piece",
    "pilot", "pinch", "pixel", "pizza", "place", "plain", "plane", "plant",
    "plate", "plaza", "plead", "plumb", "plume", "plump", "plunge","point",
    "polar", "porch", "pouch", "pound", "power", "press", "price", "pride",
    "prime", "prince","print", "prior", "prize", "probe", "prone", "proof",
    "proud", "prove", "proxy", "psalm", "pulse", "punch", "pupil", "purse",
    "queen", "query", "quest", "queue", "quick", "quiet", "quota", "quote",
    "radar", "radio", "raise", "rally", "ranch", "range", "rapid", "ratio",
    "reach", "react", "ready", "realm", "rebel", "refer", "reign", "relax",
    "relay", "renew", "reply", "rider", "ridge", "rifle", "right", "rigid",
    "risky", "rival", "river", "robin", "robot", "rocky", "roman", "roost",
    "rouge", "rough", "round", "route", "royal", "rugby", "ruler", "rural",
    "sadly", "saint", "salad", "scale", "scare", "scene", "scope", "score",
    "scout", "scrap", "sense", "serve", "setup", "seven", "shade", "shaft",
    "shake", "shall", "shame", "shape", "share", "shark", "sharp", "shear",
    "sheep", "sheer", "sheet", "shelf", "shell", "shift", "shine", "shirt",
    "shock", "shoot", "shore", "short", "shout", "shrug", "sight", "since",
    "sixth", "sixty", "sized", "skill", "skull", "slate", "slave", "sleep",
    "slice", "slide", "slope", "smart", "smell", "smile", "smoke", "snake",
    "solar", "solid", "solve", "sonic", "sorry", "sound", "south", "space",
    "spare", "spark", "speak", "spear", "speed", "spend", "spent", "spice",
    "spike", "spine", "spite", "split", "spoke", "spoon", "sport", "spray",
    "squad", "stack", "staff", "stage", "stain", "stake", "stale", "stall",
    "stamp", "stand", "stare", "stark", "start", "state", "stays", "steal",
    "steam", "steel", "steep", "steer", "stern", "stick", "stiff", "still",
    "stock", "stole", "stone", "stood", "store", "storm", "story", "stout",
    "stove", "strap", "straw", "stray", "strip", "stuck", "study", "stuff",
    "style", "sugar", "suite", "sunny", "super", "surge", "swamp", "swear",
    "sweep", "sweet", "swept", "swift", "swing", "sword", "swore", "sworn",
    "swung", "table", "taken", "taste", "teach", "teeth", "thank", "theme",
    "there", "thick", "thief", "thing", "think", "third", "thorn", "those",
    "three", "threw", "throw", "thumb", "tiger", "tight", "timer", "tired",
    "title", "today", "token", "topic", "total", "touch", "tough", "towel",
    "tower", "toxic", "trace", "track", "trade", "trail", "train", "trait",
    "trash", "treat", "trend", "trial", "tribe", "trick", "tried", "troop",
    "truck", "truly", "trump", "trunk", "trust", "truth", "tumor", "tuner",
    "twice", "twist", "ultra", "uncle", "under", "unify", "union", "unite",
    "unity", "until", "upper", "upset", "urban", "usage", "usual", "utter",
    "valid", "value", "valve", "vault", "venue", "verse", "vigor", "vinyl",
    "viral", "virus", "visit", "vista", "vital", "vivid", "vocal", "vodka",
    "voice", "voter", "wagon", "waist", "waste", "watch", "water", "weary",
    "weave", "weird", "whale", "wheat", "wheel", "where", "which", "while",
    "white", "whole", "whose", "wider", "witch", "woman", "works", "world",
    "worry", "worse", "worst", "worth", "would", "wound", "wrath", "write",
    "wrong", "wrote", "yacht", "yield", "young", "youth", "zebra",
]


def evaluate_guess(secret: str, guess: str) -> list[dict]:
    """Evaluate a Wordle guess against the secret word.

    Returns a list of 5 dicts: {"letter": "a", "status": "correct"|"present"|"absent"}
    Uses standard Wordle rules for duplicate letter handling.
    """
    secret = secret.lower()
    guess = guess.lower()
    result = [{"letter": g, "status": "absent"} for g in guess]

    # Track which secret letters are still available
    remaining = list(secret)

    # First pass: mark correct (green)
    for i in range(5):
        if guess[i] == secret[i]:
            result[i]["status"] = "correct"
            remaining[i] = None

    # Second pass: mark present (yellow)
    for i in range(5):
        if result[i]["status"] == "correct":
            continue
        if guess[i] in remaining:
            result[i]["status"] = "present"
            remaining[remaining.index(guess[i])] = None

    return result


@dataclass
class WordleGame:
    game_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    secret_word: str = ""
    guesses: list[str] = field(default_factory=list)
    feedback: list[list[dict]] = field(default_factory=list)
    won: bool = False
    finished: bool = False
    max_turns: int = 6

    def make_guess(self, guess: str) -> list[dict]:
        if self.finished:
            return []
        guess = guess.lower().strip()
        fb = evaluate_guess(self.secret_word, guess)
        self.guesses.append(guess)
        self.feedback.append(fb)
        if all(r["status"] == "correct" for r in fb):
            self.won = True
            self.finished = True
        elif len(self.guesses) >= self.max_turns:
            self.finished = True
        return fb

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "guesses": self.guesses,
            "feedback": self.feedback,
            "won": self.won,
            "finished": self.finished,
            "turn": len(self.guesses),
            "max_turns": self.max_turns,
            "secret_word": self.secret_word if self.finished else None,
        }


def new_game() -> WordleGame:
    return WordleGame(secret_word=random.choice(WORD_LIST))
