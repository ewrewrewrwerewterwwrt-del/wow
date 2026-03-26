# Route to Ítaca - An Alternate History (WIP!)

**Important Note** this game is a work in progress and is **NOT** ready to be played as of now.

A fork from the original [Petrograd 1917](https://github.com/aucchen/petrograd_1917) by Autumn Chen, with great influence from [Dynamic Social Democracy](https://github.com/originn0/dynamic_social_democracy/) by origin0.

Play it now! [broken-arrows.github.io/route_to_itaca/](https://broken-arrows.github.io/route_to_itaca/)

Or play it in Catalan! [broken-arrows.github.io/cami_a_itaca/](https://broken-arrows.github.io/cami_a_itaca/)

## Dev info

This repo is quite heavy compared to other mods or denndry games since I include a lot of the data used for fine-tuning. Feel free to only focus on the `out` and `source` folders if you're only interested in the coding itself, regardless of parameter tuning.

### Strictly required folders and files

Both the `source` folder and the `out/html` folder containt game-essential components, even if some of the contents on the latter get re-written on game build. This goes beyond broken images and assets, as many bits of the original `css`, `js`, and `html` files have been adapted to the needs of this mod. **Without those the basic game will NOT work as intended**, these do way more than just visual changes.

## Demographics, data analysis, and game-tuning simulations

For more info on demographic data origins and processing, check out the `demographics_data` folder and the README file there. Everything there is not needed to build the game though, so feel free to ignore it.

For how this historical data is tuned into an actual, usable, game engine, consult `simulations`. Fair amount of AI code there since the python files are just for playing around and not actually in use. Lots of cleaning happend to make that work in-game, so take that with a grain of salt. Read the README there for more info.

### Included Libraries

[jquery v1.11.1](https://releases.jquery.com/)

[d3.js v7](https://d3js.org)

[d3-parliament](https://github.com/geoffreybr/d3-parliament)

*Note: the `d3-parliament` and `d3-linegraph` libraries has been heavily modified for this mod. I severely recommend you don't install the original version if working with this mod's files. Just use the provided one and your life will be easier.*

### Building the game

1. Install [dendrynexus](https://github.com/aucchen/dendrynexus)

2. Run `dendrynexus make-html` in this folder. *Note: I recommend using `npm` and the `--pretty` flag to get a result as close to the real one being deployed to `github.io` as possible. I.e. just use `npm run dedrynexus make-html --pretty`.*

To update dendrynexus in `package-lock.json`, run `npm install --upgrade https://github.com/aucchen/dendrynexus`
