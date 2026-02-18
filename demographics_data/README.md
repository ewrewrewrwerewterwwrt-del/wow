
# Demographics Data: The "where did you get that fckng number?" place

Welcome, curious and probably unprepared complainer, to the `demographics_data` folder. The kitchen where the numbers used for "Route to Ítaca" were cooked. Statistical purity MAY be a distant memory, but some decisions had to be made. And hey, it's a game after all, so some sacrifices were unavoidable.

## Folder Structure

- `adjust_population_weights.py`: Since IDESCAT population processing returns roughly 10K pops per province, we need to acutally balance those numbers to get the real votes per circumscription. Here we do that based on IDESCAT census data.
- `adjust_unemployment.py`: Rebalances unemployment rates according to unemployment evolution over the years, folowing the criteria explained in the assumptions bit (trasnfers between unemployed, middle, ind, buss). For when you want your simulated misery to be a bit more statistically accurate.
- `auto_balancer.py`: Helps a ton for cooking the data. Ensures that your percentages always properly add up to 100.
- `cat_ceo_process.py`: Wrestles raw CEO survey data into something the simulation can actually use. Manual cooking is needed after that.
- `cat_pop_weights.py`: Turns IDESCAT data into population weights. Manual cooking is also needed but to a much lesser extent.
- `cat_simulation.py`: Runs the actual election simulations
- `ceo_raw/`: All the raw CEO survey CSVs (e.g., `cat_data_2012.csv`).
- `idescat_raw/`: Raw IDESCAT data (age, education, urbanization, etc.).
- `clean/`: Where cleaned, cooked, and processed data ends up (population weights, vote intentions, etc.). Files starting with `ok_` are the result of manual cooking.
- `simulation_results/`: Results from running the simulations.
- `spa_votes_raw/`: Subfolders are used to group by year, contains all raw voting data in `XML` fomrat.
- `.temp/`: Temporary files. Ignore unless you are debugging at 3am.

## Parlament Elections

### Data Sources (or the quesionable quality of the ingredients we have to deal with)

**Centre d'Estudis d'Opinio (CEO)**
Every bit of voting intention data comes from the Catalan public agency on Public Opinion. It's the only semi-neutral source that actually is transparent with their collected data in RAW, unfiltered glory. The detail of their files is actually quite impressive and the sample size is if not the best one of the most extensive of all opinion polls of the time.

*However*, I have to do a shotout to the 2012T3 dataset: a true clusterfck of misrepresentation. Just before the November '12 Parlament election, they decided to throw data quality out the window, so I had to play data surgeon, necromancer, and therapist to get anything usable. Provincial breakdowns? More like mental breakdowns (for me). Heavy cooking was required to have a more or less beliveable voting intention maping for the starting date.

**Statistical Institute of Catalonia (IDESCAT)**
The Catalan census office has, naturaly, quite an extensive data set on population, employement, and etc. However, what data they collect and how it is territorially distributed changes wildly through time. E.g. not all data sets are divided provincially (since some use Vegueries instead), and some data is only available in n-year intervals. So, to build up the actual population of each demographic in each province, some juggling was necessary:

- General population and age distribution data is from 2015 (a good middle point between 2012 and 2019).
- Unemploymenet data is from 2012 since in-game it is only used for the starting date (it should evolve according to player action).
- Idem with the share of bussiness owners, which is actually hardcoded into the `cat_pop_weights.py` data crunching scripts since its just four numbers.
- Education population weights and employment stats. I cobble together general population data from 2015 (because why not?) and employment stats from 2012 (so we can pretend to model employment changes as the years roll by). If it works, it works.

### Methodology & Assumptions (a.k.a. cooking the data)

- The unemployed demographic only represents ages 30-65.
        - Above that it's petanca people, so retired.
        - Below 30 goes to young. Yes I am generous but in all honesty I do not think it's that bad of a representation.
        - Needless to say underage folks are sorted out to not bloat the "young" demographic.
- Rural demographic is built from census data of those living in "urban" areas according to IDESCAT.
        - This makes the cut slightly differently to the rural cut I have to do for CEO data, since there I work with people living in places with less than 10k people. This is a bit below where IDESCAT draws the line, but once again what are we going to do about that.
- Bussiness demographic is created from those that report as self-employed. This needs a bit (or a lot, depending on the province) of cooking to represent higher classes.
- Middle demographic is build from IDESCAT workers education data. Depending on the province I ended up drawing the line a bit different: university education, advanced FP degrees, or old "Superior Bachelour" titles.
- Industrial demographic is bunddles those that did not make the cut. Industrial may not be the best name, since it does mix some service sector workers with traditional industrial areas, but hey it is what it is.

- Evolving (un-)employment: when unemployment drops, the new jobs get distributed super-realistically. When it grows, I take from the same place (also 11/10 realism):
        - 30% to/from industrial workers (industrial demographic)
        - 55% to/from middle class workers (middle demographic)
        - 15% to/from new business owners (business demographic)

Is this perfect? Absolutely not. Is it good enough for a simulation? Hopefully.

### Simulation

The election simulation bit is actually the most realistic part. Voting intention is paired with demographic weights, and then real seat allocation using both the 3% electoral threshold and d'Hont law is used. Provincial seats are spread like IRL, so there's nothing else to say.

### How-to - Parlament

1. **Prepare Data:** Drop new raw files into `ceo_raw/` or `idescat_raw/` as needed, assuming you don't like what's already there.
2. **Run the Scripts:** Fire up the Python scripts to process and clean the data. Outputs land in `clean/`. If something breaks, blame the CEO or IDESCAT.
3. **Simulate:** Pókemon-go-to-the-polls with `cat_simulation.py`. Results go to `simulation_results/`.

## Congreso Elections

In the Congreso election simulation, things are easier because I'm not bothering with demographic data as detailed as in the Parlament. Instead, let's just worry about total votes and abstentions per party, for the relevant demographics.
Voting results from **El País Election results (Congreso)**. The fact that El País published the results in relatively-easy-to-process XML helps out here.

### The enormous (over)simplifications

- As mentioned, no demographics classes are really used.
- Circumscriptions are very over-simplified. The simulation only on an Autonomous Comunity level, and only for relevant communities that truly have distinct votting patterns that may be relevant game-wise. These are: Catalunya (duh), València, Balears, Navarra, Euskadi, and Galicia. The rest is bunched together as "rest".
- This, of course, means that *some* small regional parties need special attention to get their seats. These are assigned based on fixed percentages based on their total share of "rest" votes.

        - D'Hont Law is still applied as it yields the most realistic results. However, the provincial threshold step is skipped not only because it is non-sensical for the scale the simulation is running, but also because historically it has not mattered (it has only once denied a party its otherwise assigned seat).
        - Bundling stuff up into one giant "rest" province is not great for d'Hont law, so instead there's a virtual simulation of smaller provinces to ensure the system still favours larger parties as if it was the real thing.
        - Since that virtualization is actually not enough to still have pp/psoe dominance boost, a penalty/boost for rural/cities virtual provinces is needed, which actually does help reflect general "tactical voting" tendencies in rural Spain.
        - Minor parties in the "rest" bundle (CC, PRC, ¡TE!) also need special reservation of seats to ensure they do have a chance of getting theirs.
        - Having single-division for the actual communities that are tracked is also not great, as it makes things like BNG and ERC get *some* seats easier. In the grand scheme of things, though, I've decided it's kinda fine.
        
- Regional versions of the party (PSOE variants), and whatever Podemos was doing with presenting a thousand different parties is simplified into block parties.

### How-to - Congreso

1. **Prepare Data:** Again, assuming you don't like the collected data, drop the new one in `spa_votes_raw/[relevant_year]/`
2. **Run the Scripts:**  Use `spa_preprocess.py`, which drops new stuff into `clean/`.
3. **Simulate:** Use `spa_simulation.py`. Results (you guessed it) go to `simulation_results/`.

### Future?

One probably wants to re-use the complex demographic build-up we did for the Parlament but here. Not aiming to do it for all cases, but at least for Catalunya we COULD have separate voting weights for each demographic, in each province. I do welcome any PR related to this, but at the moment I will **not** be even thinking about this.

## Final Notes

- All scripts are Python, and you’ll need the usual suspects (pandas, numpy, matplotlib, etc.).
- Note that no library installation system or virtual environments are included because I was too lazy to create them. For reference I am using Python 3.12.
- For questions, complaints, or existential dread about the data, check the script comments. Maybe they help?
