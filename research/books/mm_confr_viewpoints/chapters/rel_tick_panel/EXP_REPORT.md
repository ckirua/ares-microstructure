# rel_tick_panel — EXP_REPORT

## Native spot L2 rerun
- Pooled ρ(rel_tick, spread) native=0.5 vs baseline=-0.6
- FM quoted_spread t native=2.889889768059735
- Within-venue KR-spot ρ=1.0; HL/DB in `out/rel_tick_panel/within_venue_native.json`
- Markout by rel_tick quartile (pooled + KR-spot): `out/rel_tick_panel/markout_quartile.json`

- Gate `liq.fm_rel_tick_spread`: **Hold**
- Gate `liq.rho_rel_tick_spread`: **Hold**
