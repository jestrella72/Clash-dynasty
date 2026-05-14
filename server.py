#!/usr/bin/env python3
"""
Clash Dynasty TCG - Game Server
Run with: python3 server.py
Then open http://localhost:8080 in your browser (or share your IP on local network)
"""

import http.server
import json
import random
import uuid
import threading
import time
import os
import urllib.request
from urllib.parse import urlparse, parse_qs

# Directory where server.py lives — use this for all file lookups
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── In-memory game state ────────────────────────────────────────────────────
rooms = {}   # { roomId: GameState }
lock  = threading.Lock()

ELEMENTS = ["Water", "Fire", "Earth", "Electricity", "Psychic", "Dark"]
ELEMENT_SYMBOLS = {
    "Water": "元", "Fire": "火", "Earth": "土",
    "Electricity": "雷", "Psychic": "念", "Dark": "闇"
}

# ── Card Database ────────────────────────────────────────────────────────────
# Cards are stored in cards.json — edit that file to add/change cards.
# server.py loads it at startup; restart the server to pick up changes.
_cards_path = os.path.join(BASE_DIR, 'cards.json')
with open(_cards_path, encoding='utf-8') as _f:
    CARDS = json.load(_f)

# ── Image proxy cache ─────────────────────────────────────────────────────────
# Maps card name → Google Drive fileId for server-side image fetching.
# Images are cached locally in card_images/ so they load fast after first fetch.
IMAGES_DIR = os.path.join(BASE_DIR, 'card_images')
os.makedirs(IMAGES_DIR, exist_ok=True)
CARD_FILE_IDS = {c['name']: c.get('fileId', '') for c in CARDS}

def fetch_and_cache_image(name):
    """Fetch a card image from Google Drive and cache it locally.
    Returns (bytes, content_type) or (None, None) on failure."""
    file_id = CARD_FILE_IDS.get(name, '')
    if not file_id:
        return None, None
    # Safe filename: replace special chars
    safe = name.replace('/', '_').replace('\\', '_').replace(':', '_')
    cache_path = os.path.join(IMAGES_DIR, safe + '.jpg')
    if os.path.exists(cache_path):
        with open(cache_path, 'rb') as f:
            return f.read(), 'image/jpeg'
    # Fetch from Google Drive
    url = f'https://drive.google.com/thumbnail?id={file_id}&sz=w400'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        with open(cache_path, 'wb') as f:
            f.write(data)
        return data, 'image/jpeg'
    except Exception as e:
        print(f'[img] Failed to fetch {name}: {e}')
        return None, None

# ── Starting field card per element ──────────────────────────────────────────
STARTING_FIELD = {
    "Water":       "fl06",  # The City of Rapture  (Atlantean)
    "Psychic":     "fl01",  # The Cove             (The Sinners)
    "Fire":        "fl07",  # The Fire Temple       (Inferno)
    "Electricity": "fl05",  # Sky Light City        (Lightning)
    "Dark":        "fl04",  # The Cementary         (RAD)
    "Earth":       "fl03",  # The Throne Room       (Holy Knight)
}

# ── Lives per field card (Cemetery gets 3, everyone else gets 5) ─────────────
FIELD_LIVES = {
    "fl01": 5,  # The Cove
    "fl02": 5,  # The Ruins
    "fl03": 5,  # The Throne Room
    "fl05": 5,  # Sky Light City
    "fl06": 5,  # The City of Rapture
    "fl07": 5,  # The Fire Temple
    "fl04": 3,  # The Cementary — Dark/RAD only gets 3 lives
}

# ── Helper: build deck from deck-builder saved deckMap {name: count} ─────────
def build_deck_from_saved(deck_map):
    """Convert deck-builder deckMap {card_name: count} → shuffled list of card IDs."""
    name_to_id = {c["name"]: c["id"] for c in CARDS}
    ids = []
    for name, count in deck_map.items():
        cid = name_to_id.get(name)
        if cid:
            ids.extend([cid] * int(count))
    random.shuffle(ids)
    return ids

def detect_element_from_saved(deck_map):
    """Auto-detect the primary element from a deckMap {name: count}."""
    name_to_card = {c["name"]: c for c in CARDS}
    el_count = {el: 0 for el in ELEMENTS}
    for name, count in deck_map.items():
        card = name_to_card.get(name)
        if card:
            el = card.get("element")
            if el in ELEMENTS:
                el_count[el] = el_count.get(el, 0) + int(count)
    best = max(el_count, key=el_count.get)
    return best if el_count[best] > 0 else "Water"

def element_from_field_card(field_card_name):
    """Return the element for a field card by name (e.g. 'The Fire Temple' → 'Fire').
    Returns None if the name is None or not found."""
    if not field_card_name:
        return None
    for c in CARDS:
        if c.get("name") == field_card_name and c.get("type") == "Field":
            el = c.get("element")
            if el in ELEMENTS:
                return el
    return None

# ── Helper: build a starter deck ─────────────────────────────────────────────
def build_deck(element_choice):
    """Build a 40-card starter deck by element.
    Field cards are EXCLUDED — they are auto-placed at game start, never in the draw pile.
    """
    element_map = {
        # Water — Atlantean characters + water triggers/events
        "Water": ["at01","at02","at03","at04","at05","at06","at07","at08","at09","at10",
                  "at11","at12","at13","at14","at15","ev01","ev02","ev03","tr01","tr02","tr03","tr04"],
        # Fire — Inferno characters + fire triggers/events
        "Fire":  ["if01","if02","if03","if04","if05","if06","if07","if08","if09","if10",
                  "if11","if12","if13","if14","if15","ev01","ev03","ev06","tr02","tr06"],
        # Earth — Holy Knight characters + earth triggers/events
        "Earth": ["hk01","hk02","hk03","hk04","hk05","hk06","hk07","hk08","hk09","hk10",
                  "hk11","hk12","hk13","hk14","hk15","ev01","ev03","ev04","tr02","tr03",
                  "tr06","tr08"],
        # Electricity — Lightning characters + electricity events
        "Electricity": ["lt01","lt02","lt03","lt04","lt05","lt06","lt07","lt08","lt09","lt10",
                  "lt11","lt12","lt13","lt14","lt15","ev01","ev04","ev05","ev07","tr02","tr04"],
        # Psychic — Psychic characters + psychic events/triggers
        "Psychic": ["ps01","ps02","ps03","ps04","ps05","ps06","ps07","ps08","ps09","ps10",
                    "ps11","ps12","ps13","ps14","ps15","ps16","ps17","ev01","ev07","tr02","tr05"],
        # Dark — Mercenary + RAD characters + dark events/triggers
        "Dark": ["mc01","mc02","mc03","mc04","mc05","mc06","mc07","mc08","mc09","mc10",
                 "mc11","mc12","mc13","mc14","mc15","rd01","rd02","rd03","rd04","rd05",
                 "rd06","rd07","rd08","rd09","rd10","rd11","rd12","rd13","rd14","rd15",
                 "ev01","ev06","ev08","tr07"],
    }
    pool = element_map.get(element_choice, element_map["Water"])
    deck_ids = (pool * 4)[:40]
    random.shuffle(deck_ids)
    return deck_ids

# ── Build game state ──────────────────────────────────────────────────────────
def make_starting_fc(element):
    """Return a pre-placed field card (never destroyed, tracks lives)."""
    fc_id = STARTING_FIELD.get(element, "fl01")
    lives = FIELD_LIVES.get(fc_id, 5)
    return {"cardId": fc_id, "charged": True, "hp": lives, "maxHp": lives}

def make_player(pid, element):
    deck_ids = build_deck(element)
    hand = deck_ids[:5]
    rest = deck_ids[5:]
    fc_id = STARTING_FIELD.get(element, "fl01")
    lives = FIELD_LIVES.get(fc_id, 5)
    # Start with 0 elements — gain 1 of your choice each beginning phase
    el_zero = {"Water":0,"Fire":0,"Earth":0,"Electricity":0,"Psychic":0,"Dark":0}
    return {
        "id": pid,
        "element": element,
        "elements":    {**el_zero},  # current spendable pool (refills from bank each turn)
        "elementBank": {**el_zero},  # permanent bank — grows +1 per turn, caps at 6 total
        "gainedElementThisTurn": False,
        "hand": hand,
        "deck": rest,
        "field":   [],
        "storage": [],
        "storesThisTurn": 0,
        "extraStores": 0,
        "trash": [],
        "lives": lives,
    }

def make_game(p1_element, p2_element):
    p1id = str(uuid.uuid4())[:8]
    p2id = str(uuid.uuid4())[:8]
    return {
        "gameId": str(uuid.uuid4())[:8],
        "phase": "beginning",
        "turn": 1,
        "activePlayer": 0,
        "started": False,
        "winner": None,
        "fieldCards": [make_starting_fc(p1_element), make_starting_fc(p2_element)],
        "pendingAttack": None,  # {attackerIid, attackerPi, damage, targetType, attackerName}
        "peekedCard": None,     # top-of-deck card ID shown to P1 on turn 1 (not drawn)
        "log": ["Game started! Player 1 goes first."],
        "players": [
            make_player(p1id, p1_element),
            make_player(p2id, p2_element),
        ],
        "p1_secret": p1id,
        "p2_secret": p2id,
    }

def card_by_id(cid):
    for c in CARDS:
        if c["id"] == cid:
            return c
    return {"id": cid, "name": cid, "type": "Unknown", "cost": 0, "element": "Any",
            "effect": "", "art": "?", "color": "#333"}

def get_player_index(game, secret):
    if game["p1_secret"] == secret:
        return 0
    if game["p2_secret"] == secret:
        return 1
    return -1

# ── Game Actions ──────────────────────────────────────────────────────────────
def action_end_turn(game, player_idx):
    if game["activePlayer"] != player_idx:
        return False, "Not your turn"
    p = game["players"][player_idx]
    # Recharge all characters and field card; clear justDeployed
    for c in p["field"]:
        c["charged"] = True
        c["justDeployed"] = False
    my_fc = game["fieldCards"][player_idx]
    if my_fc: my_fc["charged"] = True
    # Reset stores counters for this player
    p["storesThisTurn"] = 0
    p["extraStores"] = 0
    p["gainedElementThisTurn"] = False
    # Switch turn
    game["activePlayer"] = 1 - player_idx
    game["phase"] = "beginning"
    game["turn"] += 1
    op = game["players"][1 - player_idx]
    op["gainedElementThisTurn"] = False
    # Refill opponent's element pool from their bank (like mana refill each turn)
    # Elements spent this turn are restored; bank only grows via gainElement
    bank = op.get("elementBank", {e: 0 for e in ELEMENTS})
    op["elements"] = {e: bank.get(e, 0) for e in ELEMENTS}
    game["log"].append(f"Player {player_idx+1} ended their turn.")
    return True, "OK"

def action_gain_element(game, player_idx, element_type):
    """Player gains 1 element of their choice (once per turn).
    Bank grows +1 per turn (max 6 total across all types).
    Current elements also get +1 immediately.
    """
    if game["activePlayer"] != player_idx:
        return False, "Not your turn"
    p = game["players"][player_idx]
    if p.get("gainedElementThisTurn"):
        return False, "Already gained an element this turn"
    if element_type not in ELEMENTS:
        return False, "Invalid element type"
    # Cap is on the BANK (permanent pool size), not current spendable
    if "elementBank" not in p:
        p["elementBank"] = {e: 0 for e in ELEMENTS}
    bank_total = sum(p["elementBank"].values())
    if bank_total >= 6:
        return False, "Element bank full (max 6 — turn 6 cap reached)"
    # Grow the bank permanently
    p["elementBank"][element_type] = p["elementBank"].get(element_type, 0) + 1
    # Also add to current spendable pool right now
    p["elements"][element_type] = p["elements"].get(element_type, 0) + 1
    p["gainedElementThisTurn"] = True
    game["log"].append(f"Player {player_idx+1} gained 1 {element_type}. Bank: {sum(p['elementBank'].values())}/6")
    return True, "OK"

def action_reset_element(game, player_idx, element_type):
    """Clear all elements of one type — player can rebuild their pool differently."""
    if game["activePlayer"] != player_idx:
        return False, "Not your turn"
    p = game["players"][player_idx]
    if element_type not in ELEMENTS:
        return False, "Invalid element type"
    count = p["elements"].get(element_type, 0)
    if count == 0:
        return False, f"No {element_type} elements to reset"
    p["elements"][element_type] = 0
    game["log"].append(f"Player {player_idx+1} reset {count} {element_type} element(s).")
    return True, "OK"

def action_play_card(game, player_idx, card_instance_id, targets=None):
    if game["activePlayer"] != player_idx:
        return False, "Not your turn"
    if game["phase"] not in ["action"]:
        return False, "Can only play cards in Action phase"
    p = game["players"][player_idx]
    if card_instance_id not in p["hand"]:
        return False, "Card not in hand"
    card = card_by_id(card_instance_id)
    # Multi-element cost check
    cost_els = card.get("cost_elements", {})
    if not cost_els:
        el = card.get("element","Any")
        cost = card.get("cost", 0)
        if cost > 0 and el not in ("Any","Mercenary"):
            cost_els = {el: cost}
        elif cost > 0:
            cost_els = {"__any__": cost}
    if "__any__" in cost_els:
        total = sum(p["elements"].values())
        needed = cost_els["__any__"]
        if total < needed:
            return False, f"Need {needed} elements (any type), have {total}"
        remaining = needed
        for etype in ELEMENTS:
            if remaining <= 0: break
            deduct = min(p["elements"].get(etype,0), remaining)
            p["elements"][etype] -= deduct
            remaining -= deduct
    elif cost_els:
        for etype, qty in cost_els.items():
            if p["elements"].get(etype, 0) < qty:
                return False, f"Need {qty} {etype} elements (have {p['elements'].get(etype,0)})"
        for etype, qty in cost_els.items():
            p["elements"][etype] -= qty
    p["hand"].remove(card_instance_id)
    if card["type"] == "Character":
        max_slots = 4
        my_fc = game["fieldCards"][player_idx]
        if my_fc:
            fc_card = card_by_id(my_fc["cardId"])
            max_slots = fc_card.get("slots", 4)
        if len(p["field"]) >= max_slots:
            return False, "Field is full"
        instance = {"cardId": card_instance_id, "charged": True, "justDeployed": True, "currentHp": card.get("hp",1), "instanceId": str(uuid.uuid4())[:6]}
        p["field"].append(instance)
        game["log"].append(f"Player {player_idx+1} played {card['name']}.")
    elif card["type"] == "Event":
        p["trash"].append(card_instance_id)
        game["log"].append(f"Player {player_idx+1} used Event: {card['name']}.")
    elif card["type"] == "Trigger":
        p["trash"].append(card_instance_id)
        game["log"].append(f"Player {player_idx+1} used Trigger: {card['name']}.")
    elif card["type"] == "Field":
        old_fc = game["fieldCards"][player_idx]
        if old_fc:
            p["trash"].append(old_fc["cardId"])
        game["fieldCards"][player_idx] = {"cardId": card_instance_id, "charged": True, "hp": card.get("hp", 4)}
        game["log"].append(f"Player {player_idx+1} played Field: {card['name']}.")
    return True, "OK"

def action_attack(game, player_idx, attacker_iid, target_type, target_ref=None):
    """attacker_iid = field instance id, target_type = 'character'|'field'"""
    if game["activePlayer"] != player_idx:
        return False, "Not your turn"
    p = game["players"][player_idx]
    op_idx = 1 - player_idx
    op = game["players"][op_idx]
    attacker = next((c for c in p["field"] if c["instanceId"] == attacker_iid), None)
    if not attacker:
        return False, "Attacker not found"
    if not attacker["charged"]:
        return False, "Character is discharged"
    if attacker.get("justDeployed"):
        return False, "This character was just deployed and cannot attack this turn"
    card = card_by_id(attacker["cardId"])
    atk = card.get("atk", 0)
    if atk == 0:
        return False, f"{card['name']} has 0 ATK and cannot attack"
    attacker["charged"] = False
    if target_type == "character" and target_ref:
        target = next((c for c in op["field"] if c["instanceId"] == target_ref), None)
        if not target:
            return False, "Target not found"
        target_card = card_by_id(target["cardId"])
        # Set pendingAttack — defender can block with storage or let the character take the hit
        game["pendingAttack"] = {
            "attackerIid":   attacker_iid,
            "attackerPi":    player_idx,
            "attackerName":  card["name"],
            "damage":        atk,
            "targetType":    "character",
            "targetRef":     target_ref,
            "targetName":    target_card["name"],
        }
        game["log"].append(f"Player {player_idx+1}'s {card['name']} attacks {target_card['name']}! Opponent may block with Storage Zone.")
    elif target_type == "field":
        # Field card attack — defender blocks with storage or loses 1 life
        op_fc = game["fieldCards"][op_idx]
        if not op_fc:
            return False, "Opponent has no field card"
        game["pendingAttack"] = {
            "attackerIid":  attacker_iid,
            "attackerPi":   player_idx,
            "attackerName": card["name"],
            "damage":       atk,
            "targetType":   "field",
        }
        game["log"].append(f"Player {player_idx+1}'s {card['name']} attacks the Field Card! Opponent may block with Storage Zone.")
    return True, "OK"

def action_set_phase(game, player_idx, phase):
    if game["activePlayer"] != player_idx:
        return False, "Not your turn"
    phases = ["beginning", "draw", "action", "ending"]
    if phase not in phases:
        return False, "Invalid phase"
    game["phase"] = phase
    game["log"].append(f"Player {player_idx+1} entered {phase.title()} Phase.")
    if phase == "draw":
        p = game["players"][player_idx]
        # P1 turn 1: peek at top card instead of drawing
        if game["turn"] == 1 and player_idx == 0:
            if p["deck"]:
                peek_id = p["deck"][0]
                game["peekedCard"] = peek_id
                peek_card = card_by_id(peek_id)
                game["log"].append(f"Player 1 peeked at the top of their deck: [{peek_card['name']}].")
            else:
                game["log"].append("Player 1's deck is empty — nothing to peek at.")
        else:
            if p["deck"]:
                p["hand"].append(p["deck"].pop(0))
                game["log"].append(f"Player {player_idx+1} drew a card.")
    if phase == "action":
        game["peekedCard"] = None   # Clear peek when moving to action
    return True, "OK"

def action_store_card(game, player_idx, card_id):
    """Store a card from hand to Storage Zone.
    - Normal: max 1 store/turn; that store draws 1 card.
    - Card effects (Spite, Gabriel, Storage Space) grant extraStores which allow
      additional stores but WITHOUT drawing.
    """
    if game["activePlayer"] != player_idx:
        return False, "Not your turn"
    p = game["players"][player_idx]
    stores_done  = p.get("storesThisTurn", 0)
    extra_stores = p.get("extraStores", 0)   # granted by card effects
    max_stores   = 1 + extra_stores           # default 1; card effects add more
    if stores_done >= max_stores:
        if extra_stores > 0:
            return False, "Already used all extra stores granted by card effects"
        return False, "Already stored this turn (max 1 without a card effect)"
    if card_id not in p["hand"]:
        return False, "Card not in hand"
    card = card_by_id(card_id)
    p["hand"].remove(card_id)
    hp = card.get("hp", 1)
    instance = {
        "cardId": card_id,
        "currentHp": hp, "maxHp": hp,
        "instanceId": str(uuid.uuid4())[:6]
    }
    p["storage"].append(instance)
    first_store = (stores_done == 0)          # only the very first store draws
    p["storesThisTurn"] = stores_done + 1
    if first_store and p["deck"]:
        drawn = p["deck"].pop(0)
        p["hand"].append(drawn)
        game["log"].append(f"Player {player_idx+1} stored {card['name']} → drew 1 card.")
    else:
        game["log"].append(f"Player {player_idx+1} stored {card['name']} (extra store via card effect, no draw).")
    return True, "OK"

def action_resolve_attack(game, player_idx, block, storage_iid=None):
    """Defender chooses to block with a Storage card or take the damage."""
    pa = game.get("pendingAttack")
    if not pa:
        return False, "No pending attack to resolve"
    defender_pi = 1 - pa["attackerPi"]
    if player_idx != defender_pi:
        return False, "Only the defender can respond"
    defender = game["players"][defender_pi]
    atk_pi   = pa["attackerPi"]

    if block and storage_iid:
        sc = next((c for c in defender["storage"] if c["instanceId"] == storage_iid), None)
        if not sc:
            return False, "Storage card not found"
        cd = card_by_id(sc["cardId"])
        if cd.get("type") not in ("Character",):
            return False, f"{cd['name']} is an {cd.get('type','?')} card — only Characters can block attacks"
        sc["currentHp"] -= 1
        if sc["currentHp"] <= 0:
            defender["storage"].remove(sc)
            defender["trash"].append(sc["cardId"])
            game["log"].append(f"Player {defender_pi+1} blocked with {cd['name']} — trashed!")
        else:
            game["log"].append(f"Player {defender_pi+1} blocked with {cd['name']} ({sc['currentHp']} HP left).")
    else:
        if pa.get("targetType") == "character" and pa.get("targetRef"):
            # Unblocked character attack — the target character takes the damage
            target = next((c for c in defender["field"] if c["instanceId"] == pa["targetRef"]), None)
            if target:
                target["currentHp"] -= pa["damage"]
                target_card = card_by_id(target["cardId"])
                game["log"].append(f"{pa['attackerName']} deals {pa['damage']} damage to {target_card['name']}!")
                if target["currentHp"] <= 0:
                    defender["field"].remove(target)
                    defender["trash"].append(target["cardId"])
                    game["log"].append(f"{target_card['name']} was destroyed and sent to Trash!")
                else:
                    game["log"].append(f"{target_card['name']} has {target['currentHp']} HP remaining.")
            else:
                game["log"].append(f"Target character not found — attack missed.")
        else:
            # Direct / field attack — reduce defender's field card HP (never removed, HP 0 = loss)
            fc = game["fieldCards"][defender_pi]
            if fc:
                fc["hp"] = max(0, fc["hp"] - 1)
                defender["lives"] = fc["hp"]
            else:
                defender["lives"] = max(0, defender["lives"] - 1)
            game["log"].append(f"Player {defender_pi+1} took damage! ({defender['lives']} lives remaining)")
            if defender["lives"] <= 0:
                game["winner"] = atk_pi
                game["log"].append(f"Player {atk_pi+1} wins!")

    game["pendingAttack"] = None
    return True, "OK"

# ── HTTP Server ───────────────────────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default request logging (we use print for actions)

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, filename, mime):
        filepath = os.path.join(BASE_DIR, filename)
        try:
            with open(filepath, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self.send_file("index.html", "text/html")
        elif path == "/deck-builder.html":
            self.send_file("deck-builder.html", "text/html")
        elif path == "/cards":
            self.send_json(CARDS)
        elif path == "/img":
            name = qs.get("name", [None])[0]
            if not name:
                self.send_response(400); self.end_headers(); return
            data, ctype = fetch_and_cache_image(name)
            if data is None:
                self.send_response(404); self.end_headers(); return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(data)
            return
        elif path == "/state":
            room_id = qs.get("room", [None])[0]
            secret  = qs.get("secret", [None])[0]
            with lock:
                if room_id not in rooms:
                    self.send_json({"error": "Room not found"}, 404); return
                game = rooms[room_id]
                pi = get_player_index(game, secret)
                if pi == -1:
                    self.send_json({"error": "Invalid secret"}, 403); return
                self.send_json({"game": sanitize(game, pi), "playerIndex": pi})
        elif path == "/rooms":
            with lock:
                available = [{"id": r, "waiting": len([
                    p for p in rooms[r]["players"] if p.get("joined")
                ]) < 2} for r in rooms if not rooms[r].get("winner")]
                self.send_json(available)
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b"{}")
        parsed = urlparse(self.path)
        path   = parsed.path

        with lock:
            if path == "/create":
                deck_map = body.get("deckMap")   # {name: count} from deck builder
                field_card_name = body.get("fieldCard")  # field card chosen in deck builder
                element = element_from_field_card(field_card_name) or (
                    detect_element_from_saved(deck_map) if deck_map else body.get("element", "Water")
                )
                room_id = str(uuid.uuid4())[:6].upper()
                game = make_game(element, "Water")  # P2 element set on join
                # Use custom deck if provided
                if deck_map:
                    p1 = game["players"][0]
                    custom = build_deck_from_saved(deck_map)
                    p1["hand"] = custom[:5]
                    p1["deck"] = custom[5:]
                game["p1_joined"] = True
                rooms[room_id] = game
                self.send_json({"roomId": room_id, "secret": game["p1_secret"], "playerIndex": 0})

            elif path == "/quickjoin":
                # Auto-join the first open room — no room code needed
                deck_map = body.get("deckMap")
                field_card_name = body.get("fieldCard")
                element = element_from_field_card(field_card_name) or (
                    detect_element_from_saved(deck_map) if deck_map else body.get("element", "Water")
                )
                open_room = next((r for r in rooms if not rooms[r].get("p2_joined") and rooms[r].get("p1_joined")), None)
                if not open_room:
                    self.send_json({"error": "No open rooms. Have P1 create a game first."}, 404); return
                room_id = open_room
                game = rooms[room_id]
                game["p2_joined"] = True
                game["started"] = True
                p2 = game["players"][1]
                p2["element"] = element
                if deck_map:
                    deck_ids = build_deck_from_saved(deck_map)
                else:
                    deck_ids = build_deck(element)
                p2["hand"] = deck_ids[:5]
                p2["deck"] = deck_ids[5:]
                p2["storesThisTurn"] = 0
                p2["extraStores"] = 0
                p2["gainedElementThisTurn"] = False
                el_zero = {"Water":0,"Fire":0,"Earth":0,"Electricity":0,"Psychic":0,"Dark":0}
                p2["elements"]    = {**el_zero}
                p2["elementBank"] = {**el_zero}
                p2["storage"] = []
                fc2_id = STARTING_FIELD.get(element, "fl01")
                p2["lives"] = FIELD_LIVES.get(fc2_id, 5)
                game["fieldCards"][1] = make_starting_fc(element)
                game["log"].append("Player 2 joined! Game begins.")
                self.send_json({"roomId": room_id, "secret": game["p2_secret"], "playerIndex": 1})

            elif path == "/join":
                room_id = body.get("roomId", "").upper()
                deck_map = body.get("deckMap")
                field_card_name = body.get("fieldCard")
                element = element_from_field_card(field_card_name) or (
                    detect_element_from_saved(deck_map) if deck_map else body.get("element", "Water")
                )
                if room_id not in rooms:
                    self.send_json({"error": "Room not found"}, 404); return
                game = rooms[room_id]
                if game.get("p2_joined"):
                    self.send_json({"error": "Room is full"}, 400); return
                game["p2_joined"] = True
                game["started"] = True
                # Rebuild P2 with chosen deck or element
                p2 = game["players"][1]
                p2["element"] = element
                if deck_map:
                    deck_ids = build_deck_from_saved(deck_map)
                else:
                    deck_ids = build_deck(element)
                p2["hand"] = deck_ids[:5]   # P2 starts with 5 cards
                p2["deck"] = deck_ids[5:]
                p2["storesThisTurn"] = 0
                p2["extraStores"] = 0
                p2["gainedElementThisTurn"] = False
                el_zero = {"Water":0,"Fire":0,"Earth":0,"Electricity":0,"Psychic":0,"Dark":0}
                p2["elements"]    = {**el_zero}   # start empty — gain 1 in beginning phase
                p2["elementBank"] = {**el_zero}   # bank also starts empty
                p2["storage"] = []
                # Set correct lives for P2's element
                fc2_id = STARTING_FIELD.get(element, "fl01")
                p2["lives"] = FIELD_LIVES.get(fc2_id, 5)
                game["fieldCards"][1] = make_starting_fc(element)
                game["log"].append("Player 2 joined! Game begins.")
                self.send_json({"roomId": room_id, "secret": game["p2_secret"], "playerIndex": 1})

            elif path == "/solo":
                dm1 = body.get("deckMap1")
                dm2 = body.get("deckMap2")
                fc1_name = body.get("fieldCard1")
                fc2_name = body.get("fieldCard2")
                el1 = element_from_field_card(fc1_name) or (
                    detect_element_from_saved(dm1) if dm1 else body.get("element1", "Water")
                )
                el2 = element_from_field_card(fc2_name) or (
                    detect_element_from_saved(dm2) if dm2 else body.get("element2", "Water")
                )
                room_id = str(uuid.uuid4())[:6].upper()
                game = make_game(el1, el2)
                game["p1_joined"] = True
                game["p2_joined"] = True
                game["started"] = True
                # Apply custom decks
                if dm1:
                    p1 = game["players"][0]
                    d1 = build_deck_from_saved(dm1)
                    p1["hand"] = d1[:5]
                    p1["deck"] = d1[5:]
                deck2 = build_deck_from_saved(dm2) if dm2 else build_deck(el2)
                p2 = game["players"][1]
                p2["element"] = el2
                p2["hand"] = deck2[:5]
                p2["deck"] = deck2[5:]
                # Also fix p2 starting field card
                game["fieldCards"][1] = make_starting_fc(el2)
                game["log"].append("Solo Practice Mode started!")
                rooms[room_id] = game
                self.send_json({
                    "roomId": room_id,
                    "secrets": {"0": game["p1_secret"], "1": game["p2_secret"]}
                })

            elif path == "/action":
                room_id = body.get("roomId")
                secret  = body.get("secret")
                act     = body.get("action")
                print(f"[ACTION] act={act!r}  keys={list(body.keys())}", flush=True)
                if room_id not in rooms:
                    self.send_json({"error": "Room not found"}, 404); return
                game = rooms[room_id]
                pi = get_player_index(game, secret)
                if pi == -1:
                    self.send_json({"error": "Auth failed"}, 403); return
                ok, msg = False, "Unknown action"
                if act == "endTurn":
                    ok, msg = action_end_turn(game, pi)
                elif act == "playCard":
                    ok, msg = action_play_card(game, pi, body["cardId"])
                elif act == "attack":
                    ok, msg = action_attack(game, pi, body["attackerIid"], body["targetType"], body.get("targetRef"))
                elif act == "setPhase":
                    ok, msg = action_set_phase(game, pi, body["phase"])
                elif act == "storeCard":
                    ok, msg = action_store_card(game, pi, body["cardId"])
                elif act == "resolveAttack":
                    ok, msg = action_resolve_attack(game, pi, body.get("block", False), body.get("storageIid"))
                elif act == "gainElement":
                    ok, msg = action_gain_element(game, pi, body.get("elementType",""))
                elif act == "resetElement":
                    ok, msg = action_reset_element(game, pi, body.get("elementType",""))
                if ok:
                    self.send_json({"ok": True, "game": sanitize(game, pi), "playerIndex": pi})
                else:
                    self.send_json({"ok": False, "error": msg})
            else:
                self.send_response(404); self.end_headers()

def sanitize(game, pi):
    """Return game state, hiding opponent's hand card identities."""
    import copy
    g = copy.deepcopy(game)
    op_idx = 1 - pi
    op = g["players"][op_idx]
    # Show opponent hand count but not card IDs
    op["handCount"] = len(op["hand"])
    op["hand"] = []
    # Remove secrets
    g.pop("p1_secret", None)
    g.pop("p2_secret", None)
    # peekedCard is only visible to P1 (player index 0)
    if pi != 0:
        g["peekedCard"] = None
    return g

if __name__ == "__main__":
    import socket
    host = "0.0.0.0"
    port = 8080
    # Allow port reuse so restart works immediately without waiting
    http.server.HTTPServer.allow_reuse_address = True
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    server = http.server.ThreadingHTTPServer((host, port), Handler)
    # Get local IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        local_ip = "localhost"
    print("=" * 50)
    print("  CLASH DYNASTY TCG — Game Server")
    print("=" * 50)
    print(f"  Local:   http://localhost:{port}")
    print(f"  Network: http://{local_ip}:{port}")
    print("  (Share the Network URL with your opponent)")
    print("=" * 50)
    print("  Press Ctrl+C to stop\n")
    server.serve_forever()
