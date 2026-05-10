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
CARDS = [
    # ── EVENT CARDS (nums 1-8) ────────────────────────────────────────────────
    {"id":"ev01","name":"Clash",            "type":"Event","cost":0,"element":"Any",
     "effect":"1 character gains +1 ATK if its ATK is 1 or less. Then draw 1 card.",
     "timing":"During Your Turn","art":"⚡","color":"#2a4a8a"},
    {"id":"ev02","name":"Cloud Rose",       "type":"Event","cost":2,"element":"Any",
     "effect":"Draw 1 card and bottom deck 1 card from your hand. Then deal 1 damage to a character.",
     "timing":"During Your Turn","art":"🌹","color":"#8a2a2a"},
    {"id":"ev03","name":"Reinforcements",   "type":"Event","cost":1,"element":"Any",
     "effect":"1 character gets +1 ATK until end of turn. Look at top 5 cards; add 1 (not Reinforcements) then rearrange.",
     "timing":"During Your Turn","art":"⚔️","color":"#2a6a2a"},
    {"id":"ev04","name":"Super-Charge",     "type":"Event","cost":1,"element":"Any",
     "effect":"You can re-charge your character or Field Card again during the turn.",
     "timing":"During Your Turn","art":"🔋","color":"#6a6a00"},
    {"id":"ev05","name":"Circuit Battery",  "type":"Event","cost":5,"element":"Electricity",
     "effect":"Recharge or reset all cards on your Field.",
     "timing":"During Your Turn","art":"🔌","color":"#1a4a6a"},
    {"id":"ev06","name":"Malfunction",      "type":"Event","cost":0,"element":"Any",
     "effect":"Drop 1 from the top of your deck, then deal 2 damage to a character on the field or Storage Zone.",
     "timing":"During Your Turn","art":"💥","color":"#4a0a4a"},
    {"id":"ev07","name":"Telekinesis",      "type":"Event","cost":0,"element":"Psychic",
     "effect":"Deal 2 damage to all characters on the Field.",
     "timing":"During Your Turn","art":"🧠","color":"#3a0a6a"},
    {"id":"ev08","name":"Assassin's Mark",  "type":"Event","cost":0,"element":"Dark",
     "effect":"Target 1 character. That character cannot attack this turn.",
     "timing":"During Your Turn","art":"🗡️","color":"#1a1a3a"},

    # ── TRIGGER CARDS (nums 9-16) ─────────────────────────────────────────────
    {"id":"tr01","name":"Cold Fusion",      "type":"Trigger","cost":0,"element":"Any",
     "effect":"Negate the activation of 1 card effect.",
     "timing":"Any Time","art":"❄️","color":"#0a4a6a"},
    {"id":"tr02","name":"Barrier",          "type":"Trigger","cost":0,"element":"Any",
     "effect":"Prevent 1 attack from being resolved. Then reduce the ATK of 1 of your characters by 1.",
     "timing":"Any Time","art":"🛡️","color":"#4a4a2a"},
    {"id":"tr03","name":"Medic Aid",        "type":"Trigger","cost":0,"element":"Earth",
     "effect":"Restore 1 health to a character.",
     "timing":"Any Time","art":"💊","color":"#2a6a2a"},
    {"id":"tr04","name":"Weather Change",   "type":"Trigger","cost":0,"element":"Any",
     "effect":"Change the active field element until end of turn.",
     "timing":"Any Time","art":"🌦️","color":"#1a5a6a"},
    {"id":"tr05","name":"Resurrection",     "type":"Trigger","cost":0,"element":"Psychic",
     "effect":"Return 1 character from your Trash to your hand.",
     "timing":"Any Time","art":"✨","color":"#5a1a8a"},
    {"id":"tr06","name":"United",           "type":"Trigger","cost":0,"element":"Any",
     "effect":"All your characters gain +1 Attack until end of turn.",
     "timing":"Any Time","art":"🤝","color":"#6a4a0a"},
    {"id":"tr07","name":"Rage",             "type":"Trigger","cost":0,"element":"Any",
     "effect":"If a player has more than 5 cards in hand, that player discards 1 card.",
     "timing":"Any Time","art":"😡","color":"#6a1a1a"},
    {"id":"tr08","name":"Storage Space",    "type":"Trigger","cost":0,"element":"Earth",
     "effect":"Store up to 2 cards from your hand in the Storage Zone.",
     "timing":"Any Time","art":"📦","color":"#4a3a1a"},

    # ── FIELD CARDS ───────────────────────────────────────────────────────────
    {"id":"fl01","name":"The Cove",         "type":"Field","cost":0,"element":"Water",
     "effect":"Spend 2 Elements: Draw 1 card from the top of your deck.",
     "timing":"During Your Turn","slots":5,"hp":5,"art":"🌊","color":"#0a2a5a"},
    {"id":"fl02","name":"The Ruins",        "type":"Field","cost":0,"element":"Earth",
     "effect":"Spend 2 Elements: Deal 1 damage to a character.",
     "timing":"During Your Turn","slots":4,"hp":5,"art":"🏚️","color":"#1a0a1a"},
    {"id":"fl03","name":"The Throne Room",  "type":"Field","cost":0,"element":"Earth",
     "effect":"Spend 2 Elements: Return 1 Trigger character card from the Trash to your hand.",
     "timing":"During Your Turn","slots":4,"hp":5,"art":"👑","color":"#2a1a0a"},
    {"id":"fl04","name":"The Cementary",    "type":"Field","cost":0,"element":"Dark",
     "effect":"Trash the top two cards from your deck, then reduce a character's value by -1 until end of turn.",
     "timing":"During Your Turn","slots":4,"hp":3,"art":"⚰️","color":"#1a0a0a"},
    {"id":"fl05","name":"Sky Light City",    "type":"Field","cost":0,"element":"Electricity",
     "effect":"Spend 2 Elements: All your characters gain +1 ATK until end of turn.",
     "timing":"During Your Turn","slots":5,"hp":5,"art":"🌆","color":"#0a0a2a"},
    {"id":"fl06","name":"The City of Rapture","type":"Field","cost":0,"element":"Water",
     "effect":"Spend 2 Elements: Draw 2 cards, then place 1 card from hand on the bottom of your deck.",
     "timing":"During Your Turn","slots":5,"hp":5,"art":"🏙️","color":"#041030"},
    {"id":"fl07","name":"The Fire Temple",   "type":"Field","cost":0,"element":"Fire",
     "effect":"Spend 2 Elements: 1 character gains +2 ATK until end of turn.",
     "timing":"During Your Turn","slots":4,"hp":5,"art":"🔥","color":"#300800"},

    # ── PSYCHIC CHARACTERS (nums 27-43) ──────────────────────────────────────
    {"id":"ps01","name":"Wrath",            "type":"Character","subtype":"Psychic","cost":3,
     "element":"Psychic","atk":2,"hp":3,"rarity":"SR",
     "effect":"[Psychic SR] When deployed, gains +2 ATK for each Psychic character in your Storage Zone.",
     "timing":"When Deployed","art":"😤","color":"#5a1a8a"},
    {"id":"ps02","name":"Greed",            "type":"Character","subtype":"Psychic","cost":3,
     "element":"Psychic","atk":1,"hp":3,"rarity":"SR",
     "effect":"[Psychic SR] Draw 2 cards. Then, your opponent discards 1 card from their hand.",
     "timing":"When Deployed","art":"💰","color":"#5a1a8a"},
    {"id":"ps03","name":"Gluttony",         "type":"Character","subtype":"Psychic","cost":3,
     "element":"Psychic","atk":2,"hp":3,"rarity":"SR",
     "effect":"[Psychic SR] Look at your opponent's hand. Choose up to 2 cards to discard.",
     "timing":"When Deployed","art":"🌀","color":"#5a1a8a"},
    {"id":"ps04","name":"Spite",            "type":"Character","subtype":"Psychic","cost":1,
     "element":"Psychic","atk":0,"hp":1,
     "effect":"[When Deployed] Look at top 5 cards of your deck. Place 1 Psychic character with cost 3 or less into your hand.",
     "timing":"When Deployed","art":"👁️","color":"#5a1a8a"},
    {"id":"ps05","name":"Fury",             "type":"Character","subtype":"Psychic","cost":2,
     "element":"Psychic","atk":1,"hp":2,
     "effect":"[When Deployed] Deal 1 damage to a character on the Field.",
     "timing":"When Deployed","art":"🔥","color":"#5a1a8a"},
    {"id":"ps06","name":"Taboo",            "type":"Character","subtype":"Psychic","cost":1,
     "element":"Psychic","atk":0,"hp":1,"keywords":["Defender"],
     "effect":"[Defender] Trash this card from your hand: Block 1 attack damage.",
     "timing":"Opponent's Turn","art":"🚫","color":"#5a1a8a"},
    {"id":"ps07","name":"Pride",            "type":"Character","subtype":"Psychic","cost":2,
     "element":"Psychic","atk":1,"hp":2,
     "effect":"[When Deployed] All your Psychic characters gain +1 ATK until end of turn.",
     "timing":"When Deployed","art":"🦚","color":"#5a1a8a"},
    {"id":"ps08","name":"Malevolent",       "type":"Character","subtype":"Psychic","cost":2,
     "element":"Psychic","atk":1,"hp":2,"keywords":["Only Once"],
     "effect":"[Only Once] Negate 1 character effect activation.",
     "timing":"Any Time","art":"😈","color":"#5a1a8a"},
    {"id":"ps09","name":"Savage",           "type":"Character","subtype":"Psychic","cost":1,
     "element":"Psychic","atk":1,"hp":1,
     "effect":"[When Deployed] This character can attack the turn it is deployed.",
     "timing":"When Deployed","art":"🔮","color":"#5a1a8a"},
    {"id":"ps10","name":"Victorious",       "type":"Character","subtype":"Psychic","cost":2,
     "element":"Psychic","atk":1,"hp":2,
     "effect":"[When Deployed] Draw 1 card for each character your opponent controls.",
     "timing":"When Deployed","art":"🏆","color":"#5a1a8a"},
    {"id":"ps11","name":"Rage (Psychic)",   "type":"Character","subtype":"Psychic","cost":2,
     "element":"Psychic","atk":2,"hp":2,
     "effect":"[Psychic Character] When deployed, destroy 1 card in the Storage Zone.",
     "timing":"When Deployed","art":"💢","color":"#5a1a8a"},
    {"id":"ps12","name":"Malice",           "type":"Character","subtype":"Psychic","cost":2,
     "element":"Psychic","atk":1,"hp":2,
     "effect":"[When Deployed] Deal 1 damage to all characters on the Field.",
     "timing":"When Deployed","art":"☠️","color":"#5a1a8a"},

    # ── MERCENARY CHARACTERS (nums 45-57) ─────────────────────────────────────
    {"id":"mc01","name":"Cain",             "type":"Character","subtype":"Mercenary","cost":6,
     "element":"Dark","atk":2,"hp":2,"rarity":"SR",
     "effect":"Discharge your Field Card. Remove all characters with 1 or less ATK from a player's Storage Zone. Then draw 2 cards.",
     "timing":"When Deployed","art":"💣","color":"#1a1a1a"},
    {"id":"mc02","name":"Noah",             "type":"Character","subtype":"Mercenary","cost":5,
     "element":"Mercenary","atk":1,"hp":2,"rarity":"SR",
     "cost_elements":{"Earth":4,"Electricity":1},
     "effect":"[Mercenary SR] Return up to 2 Mercenary characters from your Trash to your hand.",
     "timing":"When Deployed","art":"⛵","color":"#3a3a3a"},
    {"id":"mc03","name":"Mary",             "type":"Character","subtype":"Mercenary","cost":1,
     "element":"Dark","atk":0,"hp":1,
     "effect":"[When Deployed] Add 1 Mercenary character with cost 2 or less from your deck to your hand.",
     "timing":"When Deployed","art":"🌸","color":"#3a3a3a"},
    {"id":"mc04","name":"Abel",             "type":"Character","subtype":"Mercenary","cost":1,
     "element":"Dark","atk":0,"hp":2,
     "effect":"[When Deployed] Move 1 Mercenary character with cost 2 or less from your deck or Storage Zone to your hand.",
     "timing":"When Deployed","art":"🗡️","color":"#3a3a3a"},
    {"id":"mc05","name":"Aaron",            "type":"Character","subtype":"Mercenary","cost":1,
     "element":"Dark","atk":0,"hp":1,
     "effect":"[When Deployed] Look at the top 3 cards of your deck. Add 1 Mercenary to your hand.",
     "timing":"When Deployed","art":"🎯","color":"#3a3a3a"},
    {"id":"mc06","name":"Azrael",           "type":"Character","subtype":"Mercenary","cost":4,
     "element":"Dark","atk":2,"hp":3,"rarity":"SR",
     "effect":"[Mercenary SR] Destroy 1 character on the Field.",
     "timing":"When Deployed","art":"👼","color":"#1a1a2a"},
    {"id":"mc07","name":"Gabriel",          "type":"Character","subtype":"Mercenary","cost":1,
     "element":"Earth","atk":0,"hp":2,
     "effect":"[When Deployed] Store 1 Mercenary character from your hand in the Storage Zone.",
     "timing":"When Deployed","art":"🎺","color":"#3a3a3a"},
    {"id":"mc08","name":"Ariel",            "type":"Character","subtype":"Mercenary","cost":1,
     "element":"Earth","atk":0,"hp":1,
     "effect":"Look at the top 4 cards of your deck. Store 1 Mercenary character, excluding Ariel. Place remaining cards on bottom.",
     "timing":"When Deployed","art":"🌬️","color":"#3a3a3a"},
    {"id":"mc09","name":"Raziel",           "type":"Character","subtype":"Mercenary","cost":1,
     "element":"Dark","atk":0,"hp":2,"keywords":["Defender"],
     "effect":"[Defender] Trash from hand: Block 1 attack damage. Then increase a character's ATK by 1.",
     "timing":"Opponent's Turn","art":"🔫","color":"#3a3a3a"},
    {"id":"mc10","name":"Engel",            "type":"Character","subtype":"Mercenary","cost":1,
     "element":"Earth","atk":0,"hp":1,
     "effect":"[When Deployed] Draw 1 card.",
     "timing":"When Deployed","art":"🪶","color":"#3a3a3a"},
    {"id":"mc11","name":"Raphael",          "type":"Character","subtype":"Mercenary","cost":1,
     "element":"Earth","atk":0,"hp":2,
     "effect":"[When Deployed] Return 1 Mercenary from your Trash to your Storage Zone.",
     "timing":"When Deployed","art":"🌿","color":"#3a3a3a"},

    # ── LIGHTNING CHARACTERS (nums 68-69) ─────────────────────────────────────
    {"id":"lt01","name":"Saturn",           "type":"Character","subtype":"Lightning","cost":2,
     "element":"Electricity","atk":1,"hp":2,
     "effect":"[When Deployed] Give 1 character +1 ATK this turn.",
     "timing":"When Deployed","art":"🪐","color":"#1a5a6a"},
    {"id":"lt02","name":"Titan",            "type":"Character","subtype":"Lightning","cost":3,
     "element":"Electricity","atk":2,"hp":2,
     "effect":"[When Deployed] All your characters gain +1 ATK until end of turn.",
     "timing":"When Deployed","art":"🌩️","color":"#1a5a6a"},

    # ── ATLANTEAN CHARACTERS — Water (nums 78-91) ─────────────────────────────
    {"id":"at01","name":"Gadeirus",         "type":"Character","subtype":"Atlantean","cost":5,
     "element":"Water","atk":2,"hp":2,"rarity":"SR",
     "effect":"Discharge all characters with value 4 or less until start of your next turn. Then Trash 1 discharged character with value 4 or less.",
     "timing":"When Deployed","art":"🔱","color":"#0a4a6a"},
    {"id":"at02","name":"Smoker",           "type":"Character","subtype":"Atlantean","cost":1,
     "element":"Water","atk":1,"hp":1,
     "effect":"Once Per Turn: Trash 1 card from hand. Look at top 5 cards of deck; add 1 Atlantean character to hand. Rearrange rest.",
     "timing":"During Your Turn","art":"💨","color":"#0a4a6a"},
    {"id":"at03","name":"Atlas",            "type":"Character","subtype":"Atlantean","cost":2,
     "element":"Water","atk":2,"hp":1,
     "effect":"[When Deployed] Trash 1 discharged character with value 2 or less from Field or Storage Zone.",
     "timing":"When Deployed","art":"🌊","color":"#0a4a6a"},
    {"id":"at04","name":"Ampheres",         "type":"Character","subtype":"Atlantean","cost":3,
     "element":"Water","atk":2,"hp":1,"rarity":"SR","keywords":["Only Once"],
     "effect":"[Only Once] Discharge 1 character with value 2 or less. Then Trash 1 discharged character with value 3 or less.",
     "timing":"Any Time","art":"🐙","color":"#0a4a6a"},
    {"id":"at05","name":"Diaprepes",        "type":"Character","subtype":"Atlantean","cost":2,
     "element":"Water","atk":1,"hp":1,"keywords":["Only Once"],
     "effect":"[Only Once] Discharge your Field Card: Play 1 Event card with value 3 or less from your hand.",
     "timing":"Any Time","art":"🌀","color":"#0a4a6a"},
    {"id":"at06","name":"Azaes",            "type":"Character","subtype":"Atlantean","cost":2,
     "element":"Water","atk":1,"hp":1,"keywords":["Only Once"],
     "effect":"[Only Once] Discharge 1 Character until start of your next turn.",
     "timing":"During Your Turn","art":"⚡","color":"#0a4a6a"},
    {"id":"at07","name":"Mestor",           "type":"Character","subtype":"Atlantean","cost":2,
     "element":"Water","atk":1,"hp":1,"keywords":["Defender"],
     "effect":"[Defender / When Deployed] Reduce value of all opponent's characters by 1. Then draw 1 card.",
     "timing":"When Deployed","art":"🛡","color":"#0a4a6a"},
    {"id":"at08","name":"Makaira",          "type":"Character","subtype":"Atlantean","cost":1,
     "element":"Water","atk":0,"hp":1,
     "effect":"[When Deployed] Draw 2 cards from top of deck. Then Trash 1 card from your hand.",
     "timing":"When Deployed","art":"🐬","color":"#0a4a6a"},
    {"id":"at09","name":"Topo",             "type":"Character","subtype":"Atlantean","cost":2,
     "element":"Water","atk":1,"hp":1,"keywords":["Defender"],
     "effect":"[Defender] When you block: Discharge 1 character with value 3 or less until end of turn.",
     "timing":"Opponent's Turn","art":"🦭","color":"#0a4a6a"},
    {"id":"at10","name":"Cerdian",          "type":"Character","subtype":"Atlantean","cost":1,
     "element":"Water","atk":0,"hp":1,
     "effect":"[When Deployed] Add 1 Event from your Storage Zone to your hand.",
     "timing":"When Deployed","art":"🐠","color":"#0a4a6a"},
    {"id":"at11","name":"Ondine",           "type":"Character","subtype":"Atlantean","cost":0,
     "element":"Water","atk":0,"hp":1,
     "effect":"[Any Time] If this card is in your hand, you may store it in the Storage Zone at any time.",
     "timing":"Any Time","art":"🧜","color":"#0a4a6a"},
    {"id":"at12","name":"Cetea",            "type":"Character","subtype":"Atlantean","cost":1,
     "element":"Water","atk":1,"hp":1,
     "effect":"[Any Time] Trash this card to Trash a discharged character in the Storage Zone.",
     "timing":"Any Time","art":"🐋","color":"#0a4a6a"},

    # ── HOLY KNIGHT CHARACTERS — Earth (nums 93-97) ───────────────────────────
    {"id":"hk01","name":"Odon",            "type":"Character","subtype":"Holy Knight","cost":6,
     "element":"Earth","atk":2,"hp":2,"rarity":"SR","keywords":["Defender","Only Once"],
     "effect":"[Defender SR / Only Once] Discharge a Field Card you control: Negate the activation of a card and Trash it.",
     "timing":"Any Time","art":"🏰","color":"#6a5a1a"},
    {"id":"hk02","name":"Heracles",         "type":"Character","subtype":"Holy Knight","cost":6,
     "element":"Earth","atk":1,"hp":2,"rarity":"SR","keywords":["Only Once"],
     "effect":"[Only Once] Play 1 Trigger card or Trigger character from Trash. Then give 1 other character +1 Health.",
     "timing":"Any Time","art":"⚔️","color":"#6a5a1a"},
    {"id":"hk03","name":"Aion",             "type":"Character","subtype":"Holy Knight","cost":2,
     "element":"Earth","atk":1,"hp":1,"keywords":["Only Once"],
     "effect":"[Only Once] Trash a Trigger Card in your Storage Zone: Negate the activation of a character's effect.",
     "timing":"Any Time","art":"⏳","color":"#6a5a1a"},
    {"id":"hk04","name":"Hermes",           "type":"Character","subtype":"Holy Knight","cost":1,
     "element":"Earth","atk":0,"hp":1,
     "effect":"[When Deployed] Look at your deck. Add 1 Holy Knight character with value 3 or less to your hand (not Hermes). Shuffle deck.",
     "timing":"When Deployed","art":"🪶","color":"#6a5a1a"},
    {"id":"hk05","name":"Ares",             "type":"Character","subtype":"Holy Knight","cost":1,
     "element":"Earth","atk":0,"hp":1,
     "effect":"Bottom deck 1 card from hand. Look at top 5 cards; add 1 Trigger card to hand. Place rest on bottom.",
     "timing":"During Your Turn","art":"🛡️","color":"#6a5a1a"},

    # ── INFERNO CHARACTERS — Fire (nums 109, 118, 119, 122) ──────────────────
    {"id":"if01","name":"Napu",             "type":"Character","subtype":"Inferno","cost":2,
     "element":"Fire","atk":1,"hp":1,
     "effect":"Once Per Turn: When you attack a character, store top card of deck. Then may return a character from Storage Zone to hand.",
     "timing":"During Your Turn","art":"🌋","color":"#6a1a0a"},
    {"id":"if02","name":"Komodo",           "type":"Character","subtype":"Inferno","cost":0,
     "element":"Fire","atk":0,"hp":1,
     "effect":"[Any Time] Bottom deck 1 character with value 2 or less from field. Then trash this card.",
     "timing":"Any Time","art":"🦎","color":"#6a1a0a"},
    {"id":"if03","name":"Crow",             "type":"Character","subtype":"Inferno","cost":2,
     "element":"Fire","atk":1,"hp":1,
     "effect":"[When Deployed] Draw 2 cards. Place 1 card from hand on bottom of deck. Reduce value of all opponent's Field characters by 2.",
     "timing":"When Deployed","art":"🐦","color":"#6a1a0a"},
    {"id":"if04","name":"Leo",              "type":"Character","subtype":"Inferno","cost":6,
     "element":"Fire","atk":1,"hp":2,"rarity":"SR",
     "effect":"[When Deployed] Play up to 2 characters with value 2 or less from Trash. Your characters can attack this turn (except Leo).",
     "timing":"When Deployed","art":"🦁","color":"#6a1a0a"},

    # ── RAD CHARACTERS — Dark (nums 125, 127, 130, 131, 133) ─────────────────
    {"id":"rd01","name":"Boron",            "type":"Character","subtype":"RAD","cost":2,
     "element":"Dark","atk":1,"hp":1,
     "effect":"[When Deployed] Discard 2 cards from a Player's hand if they have 7+. If discarded from top of deck, -1 health to a character.",
     "timing":"When Deployed","art":"🧪","color":"#1a4a1a"},
    {"id":"rd02","name":"Neon",             "type":"Character","subtype":"RAD","cost":1,
     "element":"Dark","atk":0,"hp":1,
     "effect":"[When Deployed] Look at bottom 3 cards of deck. Choose 1 RAD character with value 3 or less to store; rearrange rest on top.",
     "timing":"When Deployed","art":"💡","color":"#1a4a1a"},
    {"id":"rd03","name":"Silver",           "type":"Character","subtype":"RAD","cost":3,
     "element":"Dark","atk":1,"hp":1,"rarity":"SR",
     "effect":"[On Removal] If removed by battle, your Field Card gains 1 life. If discarded from top of deck, reduce a character's Health by 1.",
     "timing":"On Removal","art":"☣️","color":"#1a4a1a"},
    {"id":"rd04","name":"Xenon",            "type":"Character","subtype":"RAD","cost":1,
     "element":"Dark","atk":1,"hp":1,"keywords":["Only Once"],
     "effect":"[Only Once] Bottom deck up to 4 RAD cards from Trash (not Xenon). If discarded from top of deck, reduce a character's Health by 1.",
     "timing":"Any Time","art":"⚗️","color":"#1a4a1a"},
    {"id":"rd05","name":"Nitro",            "type":"Character","subtype":"RAD","cost":3,
     "element":"Dark","atk":1,"hp":2,"keywords":["Defender"],
     "effect":"[Defender / When Deployed] Discard top 2 cards of deck. Your other characters cannot be Removed from Field until your next turn.",
     "timing":"When Deployed","art":"💣","color":"#1a4a1a"},
]

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

# ── Helper: build a starter deck ─────────────────────────────────────────────
def build_deck(element_choice):
    """Build a 40-card starter deck by element.
    Field cards are EXCLUDED — they are auto-placed at game start, never in the draw pile.
    """
    element_map = {
        # Water — Atlantean characters + water triggers/events
        "Water": ["at01","at02","at03","at04","at05","at06","at07","at08","at09","at10",
                  "at11","at12","ev01","ev02","ev03","tr01","tr02","tr03","tr04"],
        # Fire — Inferno characters + fire triggers/events
        "Fire":  ["if01","if02","if03","if04","ev01","ev03","ev06","tr02","tr06"],
        # Earth — Holy Knight characters + earth triggers/events
        "Earth": ["hk01","hk02","hk03","hk04","hk05","ev01","ev03","ev04","tr02","tr03",
                  "tr06","tr08"],
        # Electricity — Lightning characters + electricity events
        "Electricity": ["lt01","lt02","ev01","ev04","ev05","ev07","tr02","tr04"],
        # Psychic — Psychic characters + psychic events/triggers
        "Psychic": ["ps01","ps02","ps03","ps04","ps05","ps06","ps07","ps08","ps09","ps10",
                    "ps11","ps12","ev01","ev07","tr02","tr05"],
        # Dark — Mercenary + RAD characters + dark events/triggers
        "Dark": ["mc01","mc02","mc03","mc04","mc05","mc06","mc07","mc08","mc09","mc10",
                 "mc11","rd01","rd02","rd03","rd04","rd05","ev01","ev06","ev08","tr07"],
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
    # Start with 1 of the deck's element type
    el_dict = {"Water":0,"Fire":0,"Earth":0,"Electricity":0,"Psychic":0,"Dark":0}
    if element in el_dict:
        el_dict[element] = 1
    return {
        "id": pid,
        "element": element,
        "elements": el_dict,
        "gainedElementThisTurn": False,
        "hand": hand,
        "deck": rest,
        "field":   [],       # [{cardId, charged, currentHp, instanceId}]
        "storage": [],       # [{cardId, currentHp, maxHp, instanceId}] — actual stored cards
        "storesThisTurn": 0, # reset each turn end; max 1 store by default
        "extraStores": 0,    # bonus stores granted by card effects (Spite/Gabriel/Storage Space)
        "trash": [],
        "lives": lives,      # synced with fieldCards[pi].hp
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
    op["gainedElementThisTurn"] = False  # opponent can choose element next turn
    game["log"].append(f"Player {player_idx+1} ended their turn.")
    return True, "OK"

def action_gain_element(game, player_idx, element_type):
    """Player gains 1 element of their choice (once per turn)."""
    if game["activePlayer"] != player_idx:
        return False, "Not your turn"
    p = game["players"][player_idx]
    if p.get("gainedElementThisTurn"):
        return False, "Already gained an element this turn"
    if element_type not in ELEMENTS:
        return False, "Invalid element type"
    total = sum(p["elements"].values())
    if total >= 10:
        return False, "Element pool full (max 10)"
    p["elements"][element_type] = p["elements"].get(element_type, 0) + 1
    p["gainedElementThisTurn"] = True
    game["log"].append(f"Player {player_idx+1} gained 1 {element_type} element.")
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
    attacker["charged"] = False
    card = card_by_id(attacker["cardId"])
    atk = card.get("atk", 0)
    if target_type == "character" and target_ref:
        target = next((c for c in op["field"] if c["instanceId"] == target_ref), None)
        if not target:
            return False, "Target not found"
        target_card = card_by_id(target["cardId"])
        defender_atk = target_card.get("atk", 0)
        # Clash — both characters deal their ATK to each other simultaneously
        target["currentHp"] -= atk
        attacker["currentHp"] -= defender_atk
        game["log"].append(f"Clash! {card['name']} ({atk} ATK) vs {target_card['name']} ({defender_atk} ATK).")
        if target["currentHp"] <= 0:
            op["field"].remove(target)
            op["trash"].append(target["cardId"])
            game["log"].append(f"{target_card['name']} was trashed!")
        if attacker["currentHp"] <= 0:
            p["field"].remove(attacker)
            p["trash"].append(attacker["cardId"])
            game["log"].append(f"{card['name']} was trashed in the clash!")
    elif target_type in ("field", "direct"):
        # Set pending attack — defender must block or take damage
        op_fc = game["fieldCards"][op_idx]
        if target_type == "field" and not op_fc:
            return False, "Opponent has no field card"
        game["pendingAttack"] = {
            "attackerIid":  attacker_iid,
            "attackerPi":   player_idx,
            "attackerName": card["name"],
            "damage":       atk,
            "targetType":   target_type,
        }
        game["log"].append(f"Player {player_idx+1}'s {card['name']} attacks! Opponent may block with Storage Zone.")
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
        sc["currentHp"] -= 1
        if sc["currentHp"] <= 0:
            defender["storage"].remove(sc)
            defender["trash"].append(sc["cardId"])
            game["log"].append(f"Player {defender_pi+1} blocked with {cd['name']} — trashed!")
        else:
            game["log"].append(f"Player {defender_pi+1} blocked with {cd['name']} ({sc['currentHp']} HP left).")
    else:
        # Take damage — reduce field card HP (field card is NEVER removed, just HP → 0 = loss)
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
                element = body.get("element", "Water")
                room_id = str(uuid.uuid4())[:6].upper()
                game = make_game(element, "Water")  # P2 element set on join
                game["p1_joined"] = True
                rooms[room_id] = game
                self.send_json({"roomId": room_id, "secret": game["p1_secret"], "playerIndex": 0})

            elif path == "/join":
                room_id = body.get("roomId", "").upper()
                element = body.get("element", "Water")
                if room_id not in rooms:
                    self.send_json({"error": "Room not found"}, 404); return
                game = rooms[room_id]
                if game.get("p2_joined"):
                    self.send_json({"error": "Room is full"}, 400); return
                game["p2_joined"] = True
                game["started"] = True
                # Rebuild P2 with chosen element
                p2 = game["players"][1]
                p2["element"] = element
                deck_ids = build_deck(element)
                p2["hand"] = deck_ids[:6]   # P2 starts with 6 cards
                p2["deck"] = deck_ids[6:]
                p2["storesThisTurn"] = 0
                p2["extraStores"] = 0
                p2["gainedElementThisTurn"] = False
                el_dict = {"Water":0,"Fire":0,"Earth":0,"Electricity":0,"Psychic":0,"Dark":0}
                if element in el_dict: el_dict[element] = 1
                p2["elements"] = el_dict
                p2["storage"] = []
                # Set correct lives for P2's element
                fc2_id = STARTING_FIELD.get(element, "fl01")
                p2["lives"] = FIELD_LIVES.get(fc2_id, 5)
                game["fieldCards"][1] = make_starting_fc(element)
                game["log"].append("Player 2 joined! Game begins.")
                self.send_json({"roomId": room_id, "secret": game["p2_secret"], "playerIndex": 1})

            elif path == "/solo":
                el1 = body.get("element1", "Water")
                el2 = body.get("element2", "Water")
                room_id = str(uuid.uuid4())[:6].upper()
                game = make_game(el1, el2)
                game["p1_joined"] = True
                game["p2_joined"] = True
                game["started"] = True
                deck2 = build_deck(el2)
                p2 = game["players"][1]
                p2["element"] = el2
                p2["hand"] = deck2[:6]
                p2["deck"] = deck2[6:]
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
