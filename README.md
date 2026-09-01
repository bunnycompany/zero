# Zero

A quiet assistant that lives on your Mac. You talk to it in plain language,
it tells you what it did, and nothing leaves the machine.

It is early. Read [What it can and can't do yet](#what-it-can-and-cant-do-yet)
before trusting it with anything you care about.

## Start it

```bash
git clone <this repo> ~/zero && cd ~/zero
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
ln -s ~/zero/scripts/zero /usr/local/bin/zero    # so you can type `zero`
zero start
```

First launch takes about a minute — it is loading a language model onto your
machine. After that:

```bash
zero help
```

## Talking to it

```bash
zero what is in my downloads folder
zero remind me to call mom at six
zero                # what it last said
zero log            # the conversation so far
zero status         # is it awake, what mode is it in
zero stop
```

## Shadow mode, and why it starts there

Out of the box Zero is in **shadow mode**: it works out what it would do, tells
you, and changes nothing. Spend a day like this — ask it things, read the
answers, decide whether you like its judgement. Nothing can break.

Letting it act for real is a deliberate step you take by hand. Zero cannot do
it for itself; the file is off-limits to the agent by design:

```bash
echo live > namespace/control/mode     # let it act
echo shadow > namespace/control/mode   # stop it acting (works instantly, mid-task)
```

`shadow` is also the panic button. It is re-read before every single action.

## Her

Her is the part of Zero that gets to know you: three questions a day, in your
own words, kept in plain files; a line that is already there when you look;
and, when you pair them, your phone and your glasses. She never speaks first
unless you raise her level by hand. See [docs/her.md](docs/her.md).

```bash
her                 what she'd say if you looked, and her question if any
her <your answer>   answer her, or ask Zero through her
her pair            add your phone        her glasses   add your Ray-Ban Display
```

## What it can and can't do yet

**Can:** answer in plain English, look through folders, read files, search,
remember things you tell it across restarts, and explain every failure instead
of going quiet. Everything it ever did is in `namespace/log/journal.ndjson`.

**Can't yet:** click things or use apps on your behalf, notice things without
being asked (it only acts when you talk to it), or run scheduled work. It is
also currently more literal than it should be — say "my Downloads folder"
rather than a vague description, and it does better.

**Two things to know before trusting it with private data:** the journal
records everything you type and every file it reads, in plain text, forever —
that is deliberate, but it means secrets typed at Zero are kept. And if you run
`scripts/serve_models.sh` to use it from a phone, that opens an unauthenticated
model server to your local network.

## Where things are

| path | what |
|---|---|
| `scripts/zero` | the command you actually use |
| `scripts/her` | Her — the getting-to-know-you side, and your other devices |
| `namespace/` | everything Zero knows and did, as plain files you can read |
| `namespace/log/journal.ndjson` | append-only record of every action |
| `brain/`, `danger_core/`, `observer/` | decide, act, watch |
| `android/` | Zero Chat, a phone client for talking to models |

Agents working on this code: read [CLAUDE.md](CLAUDE.md) first.
