# HL thin-excess + crash-share SOR / size-cap

**Track:** EXEC/SOR · **Objects:** `frag.thin_venue_crash_excess` · `frag.crash_venue_share`

## Rule sketch

When HL thin excess elevated **and** gated SSM intensity rises → cap HL inventory / aggressive takes;
prefer Deribit/Kraken. Always show HL crash share vs vol share on SOR risk strip.

## Counterfactual honesty

No fantasy cross-venue fills. Compare **venue-local** gated severity/markout on HL vs thick legs
on the same day×symbol panel. Concordance placebo fails → kill-switches stay venue-local.

## Size schedule (sketch)

| Regime | HL size mult | Thick mult |
|--------|-------------:|-----------:|
| HL co-fire | 0.25 | 1.0 |
| HL quiet | 0.75 | 1.0 |
