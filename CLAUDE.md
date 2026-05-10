# Clash Dynasty TCG — Claude Project Memory

## What This Is
A browser-based digital version of the Clash Dynasty trading card game.
- **server.py** — Python HTTP server (port 8080), holds all game state in memory
- **index.html** — Complete game frontend (single file, no framework)
- **deck-builder.html** — Separate deck builder tool
- **START GAME.bat** — Launches server + opens browser (deletes `__pycache__` first)

Start server: `python3 server.py` (or double-click START GAME.bat)
URL: `http://localhost:8080`

---

## Game Rules (as told by Jeffrey)

### Field Cards (never destroyed — act as life counters)
| Deck / Element | Field Card | Lives |
|---|---|---|
| Water / Atlantean | City of Rapture (fl06) | 5 |
| Psychic / The Sinners | The Cove (fl01) | 5 |
| Fire / Inferno | Fire Temple (fl07) | 5 |
| Electricity / Lightning | Sky Light City (fl05) | 5 |
| Earth / Holy Knights | Throne Room (fl03) | 5 |
| Dark / RAD | Cemetery (fl04) | 3 |

- Field cards auto-placed at game start — **never in the draw pile**
- Field cards never get destroyed; they track player lives
- When a field card loses all lives, that player LOSES

### Turn Structure
1. **Beginning Phase** — gain 1 element of your choice (click the SLOT orb)
2. **Draw Phase** — draw 1 card
3. **Action Phase** — play cards, attack, store
4. **Ending Phase** — end turn

### Starting Hand
- Player 1 (goes first): draw 5 cards, start with 1 element
- Player 2 (goes second): draw 6 cards, start with 1 element

### Element System (IMPORTANT — dict-based, not a single int)
- Each player has `elements: {Water:0, Fire:0, Earth:0, Electricity:0, Psychic:0, Dark:0}`
- **Once per turn**: click any element orb in the SLOT row to gain 1 of that type
- **Right-click** an orb = reset/clear all of that element type
- Cards cost SPECIFIC element types (e.g. Noah costs 4 Earth + 1 Electricity)
- Cards with `element:"Any"` can be paid with any combination of elements
- `gainedElementThisTurn` flag prevents gaining more than once per turn

### Card Costs
- Top-left number = total element cost
- Multi-element costs stored in `cost_elements` dict on the card
- Example: Noah `cost:5, cost_elements:{"Earth":4,"Electricity":1}`
- Single-element cards derive cost from their `element` field: need `cost` of that element
- "Any" element cards use total across all types

### Characters
- Cannot attack the turn they are played (discharged, shown as greyed-out with "WAIT" label)
- Recharge at start of your next turn
- HP = hearts shown on card (❤❤ = 2 HP)
- When HP reaches 0 → goes to Trash

### Storage Zone (max 4 cards)
- Store 1 card per turn by default (drag from hand to storage zone, OR click "Store Card" button)
- Storing draws 1 card from top of deck
- Card effects (Spite, Gabriel, Storage Space trigger) can grant 1 extra store — NO draw on the extra
- `storesThisTurn` counter, `extraStores` for card-effect bonus stores
- Use stored cards to **block 1 attack** — remove 1 HP from the stored card; if HP=0, goes to Trash
- Storing allowed at ANY time during your turn (beginning, draw, or action phase)
- NOT allowed during ending phase

### Attacking
- Direct attacks and field card attacks set `pendingAttack` on the game state
- Defender must respond: block with a storage card or take damage (lose 1 life)
- Attacker uses a charged field character, which becomes discharged after attacking
- Cannot attack characters the same turn you play them

### Solo Practice Mode
- `/solo` endpoint creates a room, returns both player secrets
- Frontend stores both secrets, "Switch Player" button swaps control
- One browser controls both sides

---

## Code Architecture

### server.py Key Structures

```python
# Player state
{
  "id": "...",
  "element": "Water",           # deck element
  "elements": {"Water":1, "Fire":0, ...},  # current element pool (dict!)
  "gainedElementThisTurn": False,
  "hand": ["at01", "ev02", ...],  # card IDs
  "deck": [...],
  "field": [{"cardId":"at01","charged":True,"currentHp":2,"instanceId":"abc123"}],
  "storage": [{"cardId":"at01","currentHp":2,"maxHp":2,"instanceId":"xyz456"}],
  "storesThisTurn": 0,
  "extraStores": 0,
  "trash": [...],
  "lives": 5,
}

# Game state
{
  "gameId": "...",
  "phase": "beginning",         # beginning | draw | action | ending
  "turn": 1,
  "activePlayer": 0,            # 0 or 1
  "started": False,
  "winner": None,
  "fieldCards": [fc_p1, fc_p2], # per-player field cards
  "pendingAttack": None,        # {attackerIid, attackerPi, damage, targetType, attackerName}
  "log": [...],
  "players": [p1, p2],
  "p1_secret": "...",
  "p2_secret": "...",
}

# Field card instance
{"cardId": "fl06", "charged": True, "hp": 5, "maxHp": 5}
```

### Key Constants in server.py
```python
ELEMENTS = ["Water", "Fire", "Earth", "Electricity", "Psychic", "Dark"]
STARTING_FIELD = {
    "Water": "fl06", "Psychic": "fl01", "Fire": "fl07",
    "Electricity": "fl05", "Dark": "fl04", "Earth": "fl03",
}
FIELD_LIVES = {"fl01":5,"fl02":5,"fl03":5,"fl05":5,"fl06":5,"fl07":5,"fl04":3}
```

### Server Endpoints
| Method | Path | Description |
|---|---|---|
| GET | `/` or `/index.html` | Serve game frontend |
| GET | `/cards` | Return full CARDS array |
| GET | `/state?room=X&secret=Y` | Get game state |
| GET | `/rooms` | List open rooms |
| POST | `/create` | Create room (P1) |
| POST | `/join` | Join room (P2) |
| POST | `/solo` | Solo practice mode |
| POST | `/action` | Game actions (see below) |

### Action Types (POST /action body: `{action, roomId, secret, ...}`)
| action | Extra fields | Description |
|---|---|---|
| `endTurn` | — | End current player's turn |
| `playCard` | `cardId` | Play card from hand |
| `attack` | `attackerIid, targetType, targetRef` | Attack (sets pendingAttack) |
| `resolveAttack` | `block, storageIid` | Defender blocks or takes damage |
| `setPhase` | `phase` | Advance turn phase |
| `storeCard` | `cardId` | Store card from hand (draws 1) |
| `gainElement` | `elementType` | Gain 1 element of chosen type |
| `resetElement` | `elementType` | Clear all of one element type |

### index.html Key JS Globals
```js
S = {
  roomId, secret, pi, // player index
  game,   // full game state from server
  cards,  // {id: cardData} from /cards
  sel,    // {cardId, source, iid} — selected card
  atkMode, // bool — in attack targeting mode
}
storeMode  // bool — in store-card-selection mode
soloMode   // bool — solo practice
soloSecrets // {"0": secret1, "1": secret2}
```

### Key JS Functions
- `renderGame()` — full re-render of game state
- `renderSlots(elements, myTurn, gainedElement)` — SLOT row (6 element type orbs)
- `renderEpips(id, elements, element)` — element pip display next to player name
- `renderStorage(id, storage, isMe)` — storage zone cards
- `renderFieldCard(fieldCards)` — field card display
- `renderActions(myTurn, phase, me)` — action buttons bar
- `gainElement(elementType)` — gain 1 element, calls `/action gainElement`
- `resetElement(elementType)` — clear element type, calls `/action resetElement`
- `toggleStoreMode()` — enter store-selection mode
- `storageDrop(e)` — drag-and-drop store handler
- `blockWithStorage(storageIid)` — block incoming attack
- `passDamage()` — take damage instead of blocking
- `doAct(body)` — POST to `/action`, updates `S.game`, calls `renderGame()`
- `switchSoloPlayer()` — swap P1/P2 control in solo mode

### Card Image URLs
```js
const CARD_IMGS = { /* cardName: Google Drive thumbnail URL */ }
const EL_IMG = { Water: thumb('...'), Fire: thumb('...'), ... }
// thumb(id) = `https://drive.google.com/thumbnail?id=${id}&sz=w400`
```

---

## Card Database Notes

### Factions / Subtypes
- **Atlantean** (Water element) — at01–at12
- **Inferno** (Fire element) — if01–if04
- **Holy Knights** (Earth element) — hk01–hk05
- **Lightning** (Electricity element) — lt01–lt02
- **Psychic / The Sinners** (Psychic element) — ps01–ps12
- **Mercenary** (mixed elements) — mc01–mc11
- **RAD** (Dark element) — rd01–rd05

### Field Cards
- fl01 = The Cove (Water/Psychic starting field)
- fl02 = The Ruins (Earth)
- fl03 = The Throne Room (Earth starting field)
- fl04 = The Cemetery (Dark starting field, 3 lives)
- fl05 = Sky Light City (Electricity starting field)
- fl06 = City of Rapture (Water starting field)
- fl07 = Fire Temple (Fire starting field)

### Noah (mc02) — Example Multi-Element Card
```python
{
  "id":"mc02","name":"Noah","type":"Character","subtype":"Mercenary",
  "cost":5, "cost_elements":{"Earth":4,"Electricity":1},
  "element":"Mercenary","atk":1,"hp":2,"rarity":"SR",
  "effect":"[Mercenary SR] Return up to 2 Mercenary characters from your Trash to your hand.",
  "timing":"When Deployed"
}
```

---

## Known Issues / Pending Work

1. **Element gain is choice-based but not prompted at turn start** — player must remember to click SLOT before drawing/acting. Could add a reminder toast at beginning phase.

2. **Card abilities not implemented** — Spite, Gabriel, Storage Space should grant `extraStores`. Currently these are text-only effects. Will need ability resolution system.

3. **"Look at top card" mechanic** — Player 1's first turn allows looking at top card (peek). Not yet implemented.

4. **Element choice at game start** — Both players should choose their starting element rather than auto-receiving their deck element. Currently auto-assigned.

5. **More `cost_elements` data needed** — Only Noah has explicit `cost_elements`. All other character cards derive cost from their single `element` type. Need to add multi-element costs for other cards as Jeffrey provides them.

6. **The Ruins (fl02)** — Listed as Earth element but Mercenary deck (Dark) references it. May need clarification on faction alignment.

7. **Mercenary deck element** — Mercenaries have mixed element costs. Their deck element is currently "Dark" for `build_deck` but their cards need individual `cost_elements`.

---

## Common Debug Issues
- **"Unknown action"** error → Old Python process still running. Kill all `python3.exe` / `python.exe` processes, restart.
- **`__pycache__` issue** → START GAME.bat now deletes it automatically before each launch.
- **Cards not showing images** → Google Drive thumbnail URLs; check `CARD_IMGS` and `EL_IMG` constants in index.html.
- **Two servers running** → Browser talks to old server. Use Task Manager or `taskkill /F /IM python3.exe /T`.

---

## Session History Summary
Built over multiple Cowork sessions with Jeffrey. Key milestones:
1. Basic multiplayer game loop (create/join rooms, draw/play/attack)
2. Field card lives system (never destroyed, track lives)
3. Storage zone (store cards, block attacks with them)
4. Solo practice mode (one browser, Switch Player button)
5. Card image display fix (CSS z-index bug)
6. Element orb artwork in slot tokens
7. Drag-and-drop store (drag card from hand to storage zone)
8. Multi-element cost system (dict-based, gain by choice)
9. Noah's correct stats (ATK:1, HP:2, cost 4Earth+1Electricity)
