# @0-computer/her

The npm installer for **Her** — the part of [Zero](https://github.com/bunnycompany/zero)
that gets to know you. This package does not contain Her; it gets your Mac
ready (through `@0-computer/zero`, which it depends on) and hands off.

```bash
npx @0-computer/her setup
her
```

`setup` runs the same preflight and setup as Zero (private Python at
`~/.venv`, the repo at `~/.0-computer/zero`, the model, a launchd daemon).
Then `her` shows the first thing she'd say, and her first question. Answer
it in your own words. She asks at most three a day, and she keeps your
answers verbatim, in plain files you can read or strike out.

## Your devices

| device | how | what it does |
|---|---|---|
| MacBook (Neo or any Apple silicon) | `her setup` | where she thinks. 8 GB is enough. |
| Nothing Phone (3) | `her pair`, then Pair in the Zero app | ask her from anywhere in the house; her presence on the Glyph Matrix; long-press to talk |
| Ray-Ban Meta Display | `her glasses`, add the link in the Meta AI app (Developer Mode) | one glance line on the lens, over your own wifi |
| Ray-Ban Meta (any) | pair as a Bluetooth headset to the phone | talk to her, hear her |

A phone or glasses can *ask* her anything and can never change your Mac:
anything from a device waits for a yes given at the Mac.

## Requirements

- macOS on Apple silicon, Node.js 18+, Xcode Command Line Tools
- The Android app is sideloaded from the repo (`android/`), `nothing` flavor for the Glyph toy

## License

UNLICENSED — see `package.json`. Not yet published.
