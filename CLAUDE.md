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
- Player 2 (goes second): draw 5 cards, start with 1 element

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

## Card Database Tables

### Field Cards
| ID | Name | Element | Lives | Field Ability |
|---|---|---|---|---|
| fl01 | The Cove | Water | 5 | Spend 2: Draw 1 card |
| fl02 | The Ruins | Earth | 5 | Spend 2: Deal 1 damage to a character |
| fl03 | The Throne Room | Earth | 5 | Spend 2: Return 1 Trigger char from Trash to hand |
| fl04 | The Cemetery | Dark | 3 | Trash top 2; reduce a char's value by -1 until EOT |
| fl05 | Sky Light City | Electricity | 5 | Spend 2: All your chars +1 ATK until EOT |
| fl06 | City of Rapture | Water | 5 | Spend 2: Draw 2, place 1 from hand on bottom of deck |
| fl07 | The Fire Temple | Fire | 5 | Spend 2: 1 char +2 ATK until EOT |

---

### Event Cards
| ID | Name | Cost | Element | Effect Summary |
|---|---|---|---|---|
| ev01 | Clash | 0 | Any | 1 char +1 ATK (if ATK ≤1); draw 1 |
| ev02 | Cloud Rose | 2 | Any | Draw 1, bottom 1 from hand, deal 1 damage to a char |
| ev03 | Reinforcements | 1 | Any | 1 char +1 ATK until EOT; look top 5, add 1, rearrange |
| ev04 | Super-Charge | 1 | Any | Re-charge 1 char or Field Card again this turn |
| ev05 | Circuit Battery | 5 | Electricity | Recharge or reset all cards on your Field |
| ev06 | Malfunction | 0 | Any | Drop top 1 of deck; deal 2 damage to char on Field or Storage |
| ev07 | Telekinesis | 0 | Psychic | Deal 2 damage to all characters on the Field |
| ev08 | Assassin's Mark | 0 | Dark | Target 1 char — it cannot attack this turn |

---

### Trigger Cards
| ID | Name | Cost | Element | Timing | Effect Summary |
|---|---|---|---|---|---|
| tr01 | Cold Fusion | 0 | Any | Any Time | Negate the activation of 1 card effect |
| tr02 | Barrier | 0 | Any | Any Time | Prevent 1 attack; your 1 char -1 ATK |
| tr03 | Medic Aid | 0 | Earth | Any Time | Restore 1 HP to a character |
| tr04 | Weather Change | 0 | Any | Any Time | Change active field element until EOT |
| tr05 | Resurrection | 0 | Psychic | Any Time | Return 1 char from Trash to hand |
| tr06 | United | 0 | Any | Any Time | All your chars +1 ATK until EOT |
| tr07 | Rage | 0 | Any | Any Time | If a player has 7+ cards in hand, discard 1 |
| tr08 | Storage Space | 0 | Earth | Any Time | Store up to 2 cards from hand |

---

### Psychic Characters — The Sinners (Element: Psychic)
| ID | Name | Cost | ATK | HP | Rarity | Keywords | Effect Summary |
|---|---|---|---|---|---|---|---|
| ps01 | Wrath | 3 | 2 | 3 | SR | — | +2 ATK for each Psychic in your Storage Zone |
| ps02 | Greed | 3 | 1 | 3 | SR | — | Draw 2; opponent discards 1 |
| ps03 | Gluttony | 3 | 2 | 3 | SR | — | Look at opponent's hand; discard up to 2 |
| ps04 | Spite | 1 | 0 | 1 | — | — | Look top 5; add 1 Psychic (cost ≤3) to hand |
| ps05 | Fury | 2 | 1 | 2 | — | — | Deal 1 damage to a Field char |
| ps06 | Taboo | 1 | 0 | 1 | — | Defender | Trash from hand: block 1 attack damage |
| ps07 | Pride | 2 | 1 | 2 | — | — | All your Psychic chars +1 ATK until EOT |
| ps08 | Malevolent | 2 | 1 | 2 | — | Only Once | Negate 1 character effect activation |
| ps09 | Savage | 1 | 1 | 1 | — | — | Can attack the turn it is deployed |
| ps10 | Victorious | 2 | 1 | 2 | — | — | Draw 1 card per opponent char on Field |
| ps11 | Rage | 2 | 2 | 2 | — | — | Destroy 1 card in Storage Zone |
| ps12 | Malice | 2 | 1 | 2 | — | — | Deal 1 damage to all Field characters |

---

### Mercenary Characters (Mixed Elements)
| ID | Name | Cost | Cost Elements | ATK | HP | Rarity | Keywords | Effect Summary |
|---|---|---|---|---|---|---|---|---|
| mc01 | Cain | 6 | Dark ×6 | 2 | 2 | SR | — | Discharge FC; remove chars ATK ≤1 from Storage; draw 2 |
| mc02 | Noah | 5 | Earth×4 + Elec×1 | 1 | 2 | SR | — | Return up to 2 Mercenary chars from Trash to hand |
| mc03 | Mary | 1 | Dark ×1 | 0 | 1 | — | — | Add 1 Mercenary (cost ≤2) from deck to hand |
| mc04 | Abel | 3 | Earth×2 + Elec×1 | 0 | 2 | — | — | Move 1 Mercenary (cost ≤2) from deck or Storage to hand |
| mc05 | Aaron | 2 | Earth×1 + Elec×1 | 0 | 1 | — | — | Look top 3; add 1 Mercenary to hand |
| mc06 | Azrael | 4 | Dark ×4 | 2 | 3 | SR | — | Destroy 1 character on the Field |
| mc07 | Gabriel | 1 | Earth ×1 | 0 | 2 | — | — | Store 1 Mercenary from hand in Storage Zone |
| mc08 | Ariel | 1 | Earth ×1 | 0 | 1 | — | — | Look top 4; store 1 Mercenary (not Ariel); rest on bottom |
| mc09 | Raziel | 1 | Dark ×1 | 0 | 2 | — | Defender | Trash from hand: block 1 damage; then +1 ATK to a char |
| mc10 | Engel | 1 | Earth ×1 | 0 | 1 | — | — | Draw 1 card |
| mc11 | Raphael | 1 | Earth ×1 | 0 | 2 | — | — | Return 1 Mercenary from Trash to Storage Zone |

---

### Lightning Characters (Element: Electricity)
| ID | Name | Cost | Cost Elements | ATK | HP | Rarity | Keywords | Effect Summary |
|---|---|---|---|---|---|---|---|---|
| lt01 | Saturn | 2 | Elec ×2 | 1 | 2 | — | — | Give 1 char +1 ATK this turn |
| lt02 | Titan | 3 | Elec ×3 | 2 | 2 | — | — | All your chars +1 ATK until EOT |
| lt03 | Jupiter | 2 | Elec ×2 | 1 | 1 | — | — | — |
| lt04 | Luna | 2 | Elec ×2 | 1 | 1 | — | — | — |
| lt05 | Mars | 4 | Elec ×4 | 1 | 1 | SR | — | — |
| lt06 | Mercury | 2 | Elec×1 + Earth×1 | 1 | 1 | — | Rush | Can attack turn deployed |
| lt07 | Neptune | 1 | Elec ×1 | 0 | 1 | — | — | — |
| lt08 | Pegasi | 6 | Elec×4 + Earth×2 | 2 | 1 | SR | — | — |
| lt09 | Polaris | 1 | Elec ×1 | 0 | 1 | — | — | — |
| lt10 | Sirius | 1 | Elec ×1 | 0 | 1 | — | — | — |
| lt11 | Venus | 2 | Elec ×2 | 1 | 1 | — | — | — |
| lt12 | Kepler | 2 | Elec×1 + Earth×1 | 1 | 1 | — | Defender | Blocks attacks |
| lt13 | Dagon | 5 | Elec×4 + Earth×1 | 1 | 2 | — | Rush | Can attack turn deployed |
| lt14 | Europa | 1 | Elec ×1 | 0 | 1 | — | Defender | Blocks attacks |
| lt15 | Triton | 3 | Elec×2 + Fire×1 | 1 | 1 | — | — | — |

---

### Atlantean Characters (Element: Water)
| ID | Name | Cost | Cost Elements | ATK | HP | Rarity | Keywords | Effect Summary |
|---|---|---|---|---|---|---|---|---|
| at01 | Gadeirus | 5 | Water ×5 | 2 | 2 | SR | — | Discharge all chars (value ≤4); trash 1 discharged char (≤4) |
| at02 | Smoker | 1 | Water ×1 | 1 | 1 | — | — | Trash 1 from hand; look top 5, add 1 Atlantean to hand |
| at03 | Atlas | 2 | Water ×2 | 2 | 1 | — | — | Trash 1 discharged char (value ≤2) from Field or Storage |
| at04 | Ampheres | 3 | Water ×3 | 2 | 1 | SR | Only Once | Discharge char ≤2; trash 1 discharged char ≤3 |
| at05 | Diaprepes | 2 | Water ×2 | 1 | 1 | — | Only Once | Discharge your FC: play 1 Event (cost ≤3) from hand |
| at06 | Azaes | 2 | Water ×2 | 1 | 1 | — | Only Once | Discharge 1 char until your next turn |
| at07 | Mestor | 2 | Water ×2 | 1 | 1 | — | Defender | All opponent chars -1 value; draw 1 |
| at08 | Makaira | 1 | Water ×1 | 0 | 1 | — | — | Draw 2; trash 1 from hand |
| at09 | Topo | 2 | Water×1 + Earth×1 | 1 | 1 | — | Defender | On block: discharge 1 char (value ≤3) until EOT |
| at10 | Cerdian | 1 | Water ×1 | 0 | 1 | — | — | Add 1 Event from Storage Zone to hand |
| at11 | Ondine | 0 | — | 0 | 1 | — | — | May store this card from hand at any time |
| at12 | Cetea | 1 | Water ×1 | 1 | 1 | — | — | Trash this: trash 1 discharged char in Storage Zone |

---

### Holy Knight Characters (Element: Earth)
| ID | Name | Cost | ATK | HP | Rarity | Keywords | Effect Summary |
|---|---|---|---|---|---|---|---|
| hk01 | Carth | 6 | 2 | 2 | SR | Defender, Only Once | Discharge your FC: negate 1 card effect and trash it |
| hk02 | Heracles | 6 | 1 | 2 | SR | Only Once | Play 1 Trigger from Trash; give 1 other char +1 HP |
| hk03 | Aion | 2 | 1 | 1 | — | Only Once | Trash Trigger in Storage: negate 1 char effect |
| hk04 | Hermes | 1 | 0 | 1 | — | — | Look full deck; add 1 Holy Knight (cost ≤3, not Hermes) |
| hk05 | Ares | 1 | 0 | 1 | — | — | Bottom 1 from hand; look top 5, add 1 Trigger to hand |

---

### Inferno Characters (Element: Fire)
| ID | Name | Cost | ATK | HP | Rarity | Keywords | Effect Summary |
|---|---|---|---|---|---|---|---|
| if01 | Napu | 2 | 1 | 1 | — | — | On attack: store top of deck; may return 1 from Storage to hand |
| if02 | Komodo | 0 | 0 | 1 | — | — | Bottom deck 1 char (value ≤2) from Field; trash this |
| if03 | Crow | 2 | 1 | 1 | — | — | Draw 2, place 1 on bottom; opponent's Field chars -2 value |
| if04 | Leo | 6 | 1 | 2 | SR | — | Play up to 2 chars (≤2) from Trash; your other chars can attack this turn |

---

### RAD Characters (Element: Dark)
| ID | Name | Cost | Cost Elements | ATK | HP | Rarity | Keywords | Effect Summary |
|---|---|---|---|---|---|---|---|---|
| rd01 | Boron | 2 | Dark ×2 | 1 | 1 | — | — | If opponent has 7+ cards, they discard 2 |
| rd02 | Neon | 1 | Dark ×1 | 0 | 1 | — | — | Look bottom 3; store 1 RAD (≤3); rearrange rest on top |
| rd03 | Silver | 3 | Dark ×3 | 1 | 1 | SR | — | On Removal by battle: your FC +1 life |
| rd04 | Xenon | 1 | Dark ×1 | 1 | 1 | — | Only Once | Bottom deck up to 4 RAD from Trash (not Xenon) |
| rd05 | Nitro | 3 | Dark ×3 | 1 | 2 | — | Defender | Discard top 2; your other chars can't be removed until your next turn |
| rd06 | Atom | 1 | Dark ×1 | 1 | 1 | — | — | Trash 2 from hand; draw 3 |
| rd07 | Sulfur | 3 | Earth×1 + Dark×2 | 1 | 1 | — | — | Take control of 1 opponent char (value ≤3) until next turn, then trash it |
| rd08 | Zinc | 1 | Dark ×1 | 0 | 1 | — | Defender | On block: take control of attacking char (value ≤1) |
| rd09 | Argon | 2 | Elec×1 + Dark×1 | 1 | 1 | — | — | Discard 1 from hand; take control of 1 opponent char (value ≤2) |
| rd10 | Holmium | 1 | Dark ×1 | 0 | 1 | — | — | Discard top of deck; place up to 3 RAD from Trash on bottom of deck |
| rd11 | Fermium | 1 | Dark ×1 | 0 | 1 | — | Defender | Look top 3; rearrange and place any on top or bottom |
| rd12 | Copper | 4 | Psychic×1 + Dark×3 | 2 | 1 | SR | — | Return 7 RAD from Trash to bottom of deck; discard top 3 |
| rd13 | Tin | 4 | Psychic×1 + Dark×3 | 1 | 1 | SR | — | Return 1 RAD you control to hand; play 1 RAD (cost ≤4) from Trash |
| rd14 | Manganese | 5 | Dark ×5 | 1 | 2 | SR | — | Trash 1 Field char; your FC +1 life, opponent's FC -1 life |
| rd15 | Gold | 6 | Psychic×2 + Dark×4 | 1 | 2 | SR | — | All opponent Field chars -2 value; play up to 2 RAD from Trash |

---

## Card Database Notes

### Factions / Subtypes
- **Atlantean** (Water element) — at01–at12
- **Inferno** (Fire element) — if01–if04
- **Holy Knights** (Earth element) — hk01–hk05
- **Lightning** (Electricity element) — lt01–lt15
- **Psychic / The Sinners** (Psychic element) — ps01–ps12
- **Mercenary** (mixed elements) — mc01–mc11
- **RAD** (Dark element) — rd01–rd15

### Field Cards
- fl01 = The Cove (Psychic starting field)
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
