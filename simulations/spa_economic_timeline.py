"""
spa_economic_timeline.py — Spanish political event system for calibration.

Defines:
  EVENTS_SPA           : list of event dicts (one per historical moment)
  SPA_UNEMP_OFFSET     : Spain-wide unemployment offset above Catalan values
  get_spa_gob(month)   : returns Spanish coalition list for a given month

Month 1 = Aug 2012  |  Month 88 = Nov 2019

NOTE on independence movement seasonality: economic_engine.py uses a fixed
per-year amplitude (INDY_SEASONAL_AMPLITUDE dict), while cat_engine.js uses
an adaptive amplitude based on mov_norm and trust_inv. This produces a small
divergence in independence_movement and downstream cat_spa_relations. For the
Spanish calibration this is second-order — cat_spa_relations drift is dominated
by the government pair, not the seasonal pulse.
"""

# ── MACRO OFFSETS ─────────────────────────────────────────────────────────────
# Spanish-level macro variables are derived from the Catalan engine output.
# GDP: no persistent offset (Spanish and Catalan GDP cycles track together
#      in the base engine).
# Unemployment: Spain-wide was consistently ~5 pp above Catalunya throughout
#               the 2012-2019 period.
# Welfare: no offset applied (similar trajectory).

SPA_UNEMP_OFFSET = 5.0   # percentage points above Catalan unemployment

# ── SPANISH GOVERNMENT TIMELINE ───────────────────────────────────────────────
# Determines which coalition is incumbent for GDP boost and vote effects.
# Parallel to (but separate from) the Catalan Generalitat timeline.

GOBIERNO_SPA_TIMELINE = [
    (1,  70, ['pp']),      # Rajoy PP (abs majority → care → minority, same coalition)
    (71, 88, ['psoe']),    # Sánchez PSOE minority (investiture Jun 2018, month 71)
]

def get_spa_gob(month):
    for start, end, coalition in GOBIERNO_SPA_TIMELINE:
        if start <= month <= end:
            return coalition
    return ['pp']


# ── EVENT SYSTEM ─────────────────────────────────────────────────────────────
# Each event fires at a specific month (one-time).
#
# Effect fields:
#   corruption_pp     : delta added to running corruption_pp level
#   corruption_psoe   : delta added to running corruption_psoe level
#   flag_set          : str flag name to set True in model flags dict
#   vox_init_pct      : handled specially in runner — initial Vox support
#                       injected as PP drain when vox_active is set
#   support_inject    : list of {family, c, delta, from}
#                       Transfers `delta` pp from family `from` to `family`
#                       in constituency `c` ('all' = all relevant constituencies)
#   gob_coalition     : new Spanish coalition; updates spa_flags in runner
#   navarra_nsuma     : handled specially in runner — merges pp+upn+cs into nsuma
#   flag_values       : dict of {flag_name: value} — set numeric flag values
#                       Used for leadership multipliers (psoe_leadership_mult, etc.)

EVENTS_SPA = [

    # ── BÁRCENAS LEAK (Jan 2013) ──────────────────────────────────────────────
    # El País publishes Bárcenas's secret accounts listing PP slush fund payments.
    # Immediate credibility crisis for Rajoy; voters start bleeding to CS and abs.
    {
        'id':            'barcenas_leak',
        'month':         6,   # Jan 2013
        'corruption_pp': +35,
    },

    # ── BÁRCENAS ESCALATION (Jul 2013) ───────────────────────────────────────
    # Full leaked texts of Rajoy's own bonus payments confirmed.
    # Second corruption wave; accelerates PP→CS migration in urban areas.
    {
        'id':            'barcenas_escalation',
        'month':         12,  # Jul 2013
        'corruption_pp': +15,
    },

    # ── PODEMOS EP SURGE (May 2014) ───────────────────────────────────────────
    # Podemos wins 5 seats in the EP with ~8% nationally from nowhere.
    # Enormous mobilisation of long-term abstainers + disaffected PSOE voters.
    # Real trajectory: ~2% → ~20% in 18 months. The injection is large because
    # this was an exogenous political shock, not an organic economic trend.
    # ── PODEMOS EP SURGE (May 2014) ───────────────────────────────────────────
    # Exogenous shock: 8pp of abstainers mobilised, 2pp from PSOE as a direct
    # one-time signal.  The ongoing PSOE→Podemos flow is handled organically by
    # the podemos_channeling mechanism in the vote model — no large PSOE drain
    # here to avoid locking in a permanent deficit.
    {
        'id':     'podemos_EP_surge',
        'month':  22,  # May 2014
        'support_inject': [
            {'family': 'podemos', 'c': 'all', 'delta': 9.0, 'from': 'abs'},
            {'family': 'podemos', 'c': 'all', 'delta': 2.0, 'from': 'psoe'},
        ],
    },

    # ── CS NATIONAL LAUNCH + BREAKTHROUGH (Feb–Mar 2015) ────────────────────
    # CS announces it will run state-wide for the first time (previously Catalan
    # only). Simultaneously surges to ~15% nationally. Draws anti-corruption PP
    # voters and some abstainers. Particularly strong in urban constituencies.
    # Real trajectory: ~0% → ~14% in ~6 months of national attention.
    {
        'id':       'cs_breakthrough',
        'month':    31,  # Feb 2015
        'flag_set': 'spa_cs_active',
        'support_inject': [
            {'family': 'cs', 'c': 'all', 'delta':  9.0, 'from': 'pp'},
            {'family': 'cs', 'c': 'all', 'delta':  2.0, 'from': 'abs'},
        ],
    },

    # ── CDC / UNIÓ SPLIT (Dec 2014 – Mar 2015) ───────────────────────────────
    # Unió Democràtica de Catalunya breaks from CDC over independence strategy.
    # CDC/DL loses the moderate wing: some Unió voters go to PSC, some to
    # abstention, but crucially pro-independence CDC voters shift to ERC
    # (ERC positioned as the "clean" independence party vs CDC's CiU baggage).
    # cat_conv: 22% → ~12% (-10pp);  ERC: 6% → ~10% (+4pp from cat_conv)
    {
        'id':     'cdc_unio_split',
        'month':  35,  # Feb 2015
        'support_inject': [
            {'family': 'erc',  'c': 'catalunya', 'delta': 4.0, 'from': 'cat_conv'},
            {'family': 'psoe', 'c': 'catalunya', 'delta': 2.0, 'from': 'cat_conv'},
            {'family': 'abs',  'c': 'catalunya', 'delta': 4.0, 'from': 'cat_conv'},
        ],
    },

    # ── IU RUNS SEPARATELY (Sep 2015) ────────────────────────────────────────
    # IU ran independently from Podemos in the Dec 2015 election. The left
    # space was split: Podemos (new politics) vs IU (traditional communist-left).
    # IRL: IU got 2 seats, Podemos 69. Draws from disaffected Podemos voters.
    {
        'id':       'iu_split',
        'month':    38,  # Sep 2015 (ahead of month 41 Dec 2015 election)
        'flag_set': 'spa_iu_split',
        'support_inject': [
            {'family': 'iu', 'c': 'all', 'delta': 2.0, 'from': 'abs'},
        ],
    },

    # ── ERE VERDICT (Oct 2015) ────────────────────────────────────────────────
    # Andalusia ERE corruption case verdict against PSOE officials.
    # Fires just before the Dec 2015 election — contributes to PSOE
    # underperformance vs pre-election polls.
    {
        'id':             'ere_verdict',
        'month':          39,  # Oct 2015
        'corruption_psoe': +20,
    },

    # ── UNIDOS PODEMOS — IU MERGES BACK (May 2016) ───────────────────────────
    # IU and Podemos form Unidos Podemos for the Jun 2016 election.
    # Clearing the flag removes IU from active families; its residual support
    # dissolves proportionally into the remaining pool at next renormalization
    # (equivalent to those voters scattering across the active parties).
    {
        'id':        'iu_merge',
        'month':     45,  # May 2016 — Unidos Podemos officially formed
        'flag_clear': 'spa_iu_split',
    },

    # ── PSOE LEADERSHIP CRISIS (Oct 2016) ────────────────────────────────────
    # The PSOE federal committee forces Sánchez to resign as party leader.
    # A caretaker committee takes over; the party is in open civil war.
    # PSOE voters bleed to Podemos and abstention. The leadership_mult goes
    # negative → acts as a sustained penalty instead of a recovery pull.
    {
        'id':     'psoe_crisis',
        'month':  51,  # Oct 2016
        'flag_values': {'psoe_leadership_mult': -0.5},
        'support_inject': [
            {'family': 'podemos', 'c': 'all', 'delta': 1.5, 'from': 'psoe'},
            {'family': 'abs',     'c': 'all', 'delta': 1.0, 'from': 'psoe'},
        ],
    },

    # ── SÁNCHEZ WINS PRIMARIES (Jun 2017) ─────────────────────────────────────
    # Sánchez wins the PSOE primaries in a membership vote, defeating Susana
    # Díaz. Energises the party base and signals a leftward turn. PSOE begins
    # a sustained recovery pull from abstention — mirrors psc_recovery_mult.
    {
        'id':     'sanchez_primaries',
        'month':  59,  # Jun 2017
        'flag_values': {'psoe_leadership_mult': 1.0},
    },

    # ── GÜRTEL VERDICT (May 2018) ─────────────────────────────────────────────
    # Supreme Court upholds that PP benefited from the Gürtel corruption network.
    # Directly triggers the no-confidence vote. Large corruption spike.
    {
        'id':            'gurtel_verdict',
        'month':         70,  # May 2018
        'corruption_pp': +25,
    },

    # ── SÁNCHEZ INVESTITURE (Jun 2018) ────────────────────────────────────────
    # PSOE wins no-confidence vote; Sánchez becomes PM. Coalition changes.
    # PSOE consolidates anti-PP left vote; Podemos loses the "useful" left voters.
    # Partial PSOE corruption reset (distance from ERE era, new leadership image).
    {
        'id':             'psoe_investiture',
        'month':          71,  # Jun 2018
        'gob_coalition':  ['psoe'],
        'corruption_psoe': -8,  # partial reset — ERE era associated with old guard
        'support_inject': [
            {'family': 'psoe', 'c': 'all', 'delta': 5.0, 'from': 'podemos'},
            {'family': 'psoe', 'c': 'all', 'delta': 4.0, 'from': 'abs'},
        ],
    },

    # ── CASADO TAKES PP LEADERSHIP (Jul 2018) ────────────────────────────────
    # Pablo Casado wins PP leadership election, replacing Rajoy. Younger face,
    # distance from Gürtel era, harder ideological line. PP image partly resets.
    # Partial corruption reset + sustained recovery pull from abs.
    {
        'id':             'casado_pp_leadership',
        'month':          72,  # Jul 2018
        'corruption_pp':  -15,  # partial reset — new face distances from Bárcenas/Gürtel
        'flag_values':    {'pp_leadership_mult': 1.0},
    },

    # ── ERC INDEPENDENCE SPACE REBALANCING (May 2016) ────────────────────────
    # Between Dec 2015 and Jun 2016, ERC strengthened at the expense of JxSí/
    # CDC within the independence vote.  Puigdemont's investiture (Jan 2016)
    # and his CiU-roots government signalled that CDC owned the Generalitat
    # while ERC positioned as the democratic republic party — driving ERC gains.
    {
        'id':     'erc_rebalance_2016',
        'month':  46,  # May 2016 (pre 26-J election)
        'support_inject': [
            {'family': 'erc', 'c': 'catalunya', 'delta': 2.0, 'from': 'cat_conv'},
            {'family': 'erc', 'c': 'catalunya', 'delta': 2.0, 'from': 'abs'},
        ],
    },

    # ── ERC CONSOLIDATES POST-155 (Dec 2018) ─────────────────────────────────
    # After the Oct 2017 referendum and Art. 155, ERC's strategic moderation
    # attracted diaspora pro-independence voters who distrusted JxCat's maximalism.
    # ERC went from 12 to 15 seats between 2016 and 2019.
    {
        'id':     'erc_post155_boost',
        'month':  76,  # Nov 2018 — same cycle as Vox emergence
        'support_inject': [
            {'family': 'erc', 'c': 'catalunya', 'delta': 1.5, 'from': 'cat_conv'},
            {'family': 'erc', 'c': 'catalunya', 'delta': 2.0, 'from': 'abs'},
        ],
    },

    # ── TERUEL EXISTE FORMATION (Sep 2018) ───────────────────────────────────
    # Teruel Existe emerged as a civic platform demanding investment parity for
    # the interior provinces. It decided to stand for Congress for the Apr 2019
    # election, winning 1 seat. Prior to this it had no national presence; TE
    # support is seeded from abstention (mobilised non-voters).
    # After injection, minor_reversion_rate anchors it near its new level.
    {
        'id':     'te_formation',
        'month':  73,  # Sep 2018
        'support_inject': [
            {'family': 'te', 'c': 'rest', 'delta': 0.22, 'from': 'abs'},
        ],
    },

    # ── CC CANARIAS BOOST (Jan–Feb 2019) ─────────────────────────────────────
    # Migration crisis and Canarian nationalist salience before the Apr 2019
    # election drove CC's vote up from ~80k (2016) to ~137k (2019a). The party
    # ran a strong "Canarias decides" campaign, mobilising abstainers.
    {
        'id':     'cc_canarias_boost',
        'month':  79,  # Feb 2019
        'support_inject': [
            {'family': 'cc', 'c': 'rest', 'delta': 0.38, 'from': 'abs'},
        ],
    },

    # ── PRC CANTABRIA GROWTH (Feb 2019) ──────────────────────────────────────
    # PRC had been dormant nationally but rebuilt its vote share in Cantabria
    # through regional positioning ahead of 2019. Won 1 seat in both 2019
    # elections after years without national representation.
    {
        'id':     'prc_2019_growth',
        'month':  79,  # Feb 2019
        'support_inject': [
            {'family': 'prc', 'c': 'rest', 'delta': 0.22, 'from': 'abs'},
        ],
    },

    # ── VOX EMERGENCE (Nov 2018) ──────────────────────────────────────────────
    # Vox wins 12 seats in the Andalusia regional election (2 Dec 2018).
    # Sets vox_active flag; runner injects initial Vox support as PP drain.
    # Capped at 15% of PP's current support per constituency in the runner.
    {
        'id':           'vox_emergence',
        'month':        76,   # Nov 2018
        'flag_set':     'vox_active',
        'vox_init_pct': 8.0,  # % drain target from PP per constituency (runner handles)
    },

    # ── VOX SURGE BEFORE APR 2019 ELECTION ───────────────────────────────────
    # Catalan independence crisis and right-wing consolidation campaigns
    # push Vox further. Reaches ~10% nationally just before Apr 2019 election.
    {
        'id':     'vox_surge_2019a',
        'month':  79,  # Jan 2019
        'support_inject': [
            {'family': 'vox', 'c': 'all', 'delta': 4.0, 'from': 'pp'},
            {'family': 'vox', 'c': 'all', 'delta': 0.5, 'from': 'cs'},
        ],
    },

    # ── BNG JOINS EN MAREA (Mar 2016) ─────────────────────────────────────────
    # BNG merges into the En Marea coalition with Podemos ahead of the Jun 2016
    # election. Its Galicia support transfers to the podemos family.
    # IRL: bng got 0 seats in 2016 — all absorbed into UP/En Marea (5 seats).
    {
        'id':     'bng_en_marea_merge',
        'month':  44,  # Mar 2016 (ahead of month 47 Jun 2016 election)
        'support_inject': [
            {'family': 'podemos', 'c': 'galicia', 'delta': 4.5, 'from': 'bng'},
        ],
    },

    # ── BNG SPLITS FROM EN MAREA (Mar 2019) ───────────────────────────────────
    # En Marea dissolves. BNG re-emerges as an independent party ahead of the
    # Apr 2019 election, seeded from UP (which shrinks correspondingly).
    # IRL: bng 1 seat (2019a), 2 seats (2019n); UP drops from 5 → 4 → 3 seats.
    {
        'id':     'nos_bng_split',
        'month':  80,  # Mar 2019
        'support_inject': [
            {'family': 'bng', 'c': 'galicia', 'delta': 3.0, 'from': 'podemos'},
        ],
    },

    # ── BNG CONSOLIDATES (Sep 2019) ───────────────────────────────────────────
    # BNG continued to grow between the two 2019 elections as Galician left
    # voters consolidated around the re-established BNG brand.
    # IRL: 1 seat (Apr) → 2 seats (Nov).
    {
        'id':     'bng_consolidation',
        'month':  85,  # Sep 2019
        'support_inject': [
            {'family': 'bng', 'c': 'galicia', 'delta': 2.5, 'from': 'podemos'},
        ],
    },

    # ── RIGHT CONSOLIDATION BEFORE NOV 2019 ELECTION ────────────────────────
    # Oct 2019 independence trial verdict triggers hard-right backlash.
    # CS collapses: right flank → Vox; moderate flank → PP (useful-right logic).
    # CS: 57 seats (Apr) → 10 seats (Nov) = -47.  PP +22, Vox +28 approx.
    # PP also recovers abstaining centre-right voters (tired of instability).
    # Vox deltas tuned down: sim over-predicted Vox and under-predicted CS.
    {
        'id':     'right_consolidation_2019n',
        'month':  86,  # Oct 2019
        'support_inject': [
            {'family': 'vox', 'c': 'all', 'delta': 3.5, 'from': 'cs'},   # was 4.0
            {'family': 'vox', 'c': 'all', 'delta': 2.0, 'from': 'abs'},
            {'family': 'pp',  'c': 'all', 'delta': 8.0, 'from': 'cs'},
            {'family': 'pp',  'c': 'all', 'delta': 3.0, 'from': 'abs'},
        ],
    },

    # ── MES RUNS SEPARATELY (Feb 2015) ───────────────────────────────────────
    # MÉS per Mallorca runs independently in the 2015 general election and
    # beyond.  IRL they got 0 seats but the party was a real force in Balearic
    # politics. Folded into Podemos before this point; now splits off with a
    # small seed transfer.  With dissent-driven coefficients they can build
    # toward a realistic 1-seat threshold (~12-13% in Balears) over several
    # election cycles.
    {
        'id':       'mes_split',
        'month':    31,  # Feb 2015 — same window as CS breakthrough
        'flag_set': 'spa_mes_active',
        'support_inject': [
            {'family': 'mes', 'c': 'balears', 'delta': 3.5, 'from': 'podemos'},
        ],
    },

    # ── COMPROMÍS RUNS SEPARATELY (Feb 2019) ─────────────────────────────────
    # Compromís breaks from the Podemos coalition after running jointly in
    # 2015 and 2016 ("Compromís-Podemos"). For the 2019a election they field
    # their own list in Valencia. IRL result: Compromís 2 seats, UP drops to 5.
    # Transfer is larger because the split is near-election and immediate.
    {
        'id':       'compromis_split',
        'month':    79,  # Feb 2019
        'flag_set': 'spa_compromis_active',
        'support_inject': [
            {'family': 'compromis', 'c': 'valencia', 'delta': 6.5, 'from': 'podemos'},
        ],
    },

    # ── FRONT REPUBLICÀ FORMATION (Feb 2019) ────────────────────────────────
    # Anti-capitalist pro-independence left list for the Apr 2019 election.
    # Draws from abstention and a sliver of cat_conv dissidents.
    # Won 1 seat in Apr 2019 with ~2.2% in Catalunya.
    {
        'id':       'fr_formation',
        'month':    79,  # Feb 2019
        'flag_set': 'spa_fr_active',
        'support_inject': [
            {'family': 'fr', 'c': 'catalunya', 'delta': 1.0, 'from': 'cat_conv'},
            {'family': 'fr', 'c': 'catalunya', 'delta': 1.5, 'from': 'abs'},
        ],
    },

    # ── COMPROMÍS RE-MERGES INTO UP (Aug 2019) ───────────────────────────────
    # Compromís ran independently in Apr 2019 but rejoined Unidas Podemos for
    # Nov 2019 (as "Unides Podem-EUPV"). Support returns to podemos in Valencia.
    # Done one month before the flag_clear (month 85) because the runner
    # processes support_inject after flag changes in the same tick.
    {
        'id':     'compromis_remerge',
        'month':  84,  # Aug 2019
        'support_inject': [
            {'family': 'podemos', 'c': 'valencia', 'delta': 7.0, 'from': 'compromis'},
        ],
    },

    # ── CUP REPLACES FR (Sep 2019) ───────────────────────────────────────────
    # Same political space — CUP runs for Congress for the first time in
    # Nov 2019.  FR doesn't compete; its support transfers directly to CUP.
    # CUP also mobilises extra abstainers — the CUP brand is far stronger
    # than FR's and pulls heavily from non-voters.  Won 3 seats (4.5%).
    # Compromís flag also cleared here; support already transferred at month 84.
    {
        'id':        'cup_replaces_fr',
        'month':     85,  # Sep 2019
        'flag_set':  'spa_cup_spa_active',
        'flag_clear': 'spa_fr_active',
        'support_inject': [
            # FR → CUP (full transfer, same electorate)
            {'family': 'cup_spa', 'c': 'catalunya', 'delta': 3.0, 'from': 'fr'},
            # CUP mobilises abstainers strongly — CUP brand much stronger than FR
            {'family': 'cup_spa', 'c': 'catalunya', 'delta': 4.0, 'from': 'abs'},
        ],
    },

    # ── COMPROMÍS FLAG CLEAR (Sep 2019) ──────────────────────────────────────
    {
        'id':        'compromis_flag_clear',
        'month':     85,
        'flag_clear': 'spa_compromis_active',
    },

    # ── NAVARRA NSUMA FORMATION (Jan 2019) ───────────────────────────────────
    # PP + UPN + CS merge into the NSuma coalition. Formed for the April 2019
    # election (month 81), not just November — IRL NSuma ran in both 2019
    # elections. Runner merges their Navarra support into the nsuma family.
    {
        'id':           'nsuma_formation',
        'month':        79,  # Jan 2019 (ahead of month 81 2019a election)
        'flag_set':     'spa_nsuma_formed',
        'navarra_nsuma': True,  # runner merges pp+upn+cs → nsuma in Navarra
    },

    # ── MÁS PAÍS SPLIT FROM PODEMOS (Sep 2019) ───────────────────────────────
    # Íñigo Errejón breaks from Podemos to form Más País for the Nov 2019
    # election. Green-social-liberal positioning, draws from Podemos moderates.
    # IRL: Más País 3 seats; Podemos dropped correspondingly.
    {
        'id':       'mas_pais_split',
        'month':    86,  # Sep 2019 (ahead of month 88 Nov 2019 election)
        'flag_set': 'spa_up_masq_split',
        'support_inject': [
            {'family': 'mas_pais', 'c': 'all', 'delta': 1.5, 'from': 'podemos'},
        ],
    },

]
