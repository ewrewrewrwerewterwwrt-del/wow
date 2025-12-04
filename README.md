# Route to Ítaca - An Alternate History (WIP!)

**Important Note** this game is a work in progress and is **NOT** ready to be played as of now. 

A fork from the original [Petrograd 1917](https://github.com/aucchen/petrograd_1917) by Autumn Chen, with great influence from [Dynamic Social Democracy](https://github.com/originn0/dynamic_social_democracy/) by origin0.

Play it now! [broken-arrows.github.io/route_to_itaca/](https://broken-arrows.github.io/route_to_itaca/)

Or play it in Catalan! [broken-arrows.github.io/cami_a_itaca/](https://broken-arrows.github.io/cami_a_itaca/)

## Dev info

Techincal stuff for you nerds.

### Strictly required folders and files

Both the `source` folder and the `html` folder containt game-essential components, even if some of the contents on the latter get re-written on game build. This goes beyond broken images and assets, as many bits of the original `css` and `html` files have been adapted to the needs of this mod.

## Demographics and data analysis

For more info on demographic data origins and processing, check out the `demographics_data` folder and the README file there. Everything there is not needed to build the game though, so feel free to ignore it.

### Included Libraries

[jquery v1.11.1](https://releases.jquery.com/)

[d3.js v7](https://d3js.org)

[d3-parliament](https://github.com/geoffreybr/d3-parliament)

### Building the game

1. Install [dendrynexus](https://github.com/aucchen/dendrynexus)

2. Run `dendrynexus make-html` in this folder. *Modder's note: I recommend using `npm` and the `--pretty` flag to get a result as close to the real one being deployed to `github.io` as possible. I.e. just use `npm run dedrynexus make-html -- --pretty`.*

To update dendrynexus in `package-lock.json`, run `npm install --upgrade https://github.com/aucchen/dendrynexus`