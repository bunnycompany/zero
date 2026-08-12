# @0-computer/zero

The npm installer for [Zero](https://github.com/0-computer/zero) — a quiet
assistant that lives on your Mac. This package does not contain the agent
itself; it gets your machine ready and hands off to the real thing.

## Install

```bash
npx @0-computer/zero setup
```

`setup` runs a preflight check (macOS, arm64, disk space, Xcode Command Line
Tools), then — if your Mac is ready — creates a private Python environment at
`~/.venv`, clones/updates Zero into `~/.0-computer/zero`, installs its
dependencies, downloads its model (`mlx-community/gemma-4-e2b-it-4bit`,
~3.6GB, once, with visible progress), and installs a `launchd` daemon so it
survives reboots.

Nothing here downloads the model or touches your machine at plain
`npm install` time — only `zero setup` does, and only after you run it.

## Use

```bash
zero setup      # one-time: get it ready (downloads its brain)
zero <anything> # ask it, in your own words
zero            # read the last thing it told you
zero doctor     # re-run just the preflight check
zero help       # list commands
```

Zero starts in **shadow mode**: it works out what it would do and tells you,
but changes nothing, until you deliberately write `live` to
`namespace/control/mode` inside the cloned repo. See the main repo's
[README](https://github.com/0-computer/zero#readme) for what that means and
what Zero can and can't do yet.

## Requirements

- macOS on Apple silicon (`arm64`)
- Node.js 18+
- Xcode Command Line Tools

## License

Copyright (c) 0-computer. All rights reserved.

This package is unpublished and not licensed for use, copying, modification,
or redistribution. See [`package.json`](./package.json)'s `license` field
(`UNLICENSED`).
