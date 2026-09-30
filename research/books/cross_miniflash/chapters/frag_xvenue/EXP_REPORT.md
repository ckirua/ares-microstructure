# frag_xvenue — EXP_REPORT (Pass 1+2)

Generated: 2026-09-30T18:55:11.247355+00:00  
Script: `scripts/exp_frag_xvenue.py` · Out: `out/frag_xvenue/`  
Sample: ETH+BTC · UTC 2026-09-04…10 · HL+Deribit+Kraken · complete-all-3 days used for H^v

## Pass 1

| Metric | Value |
|--------|------:|
| Complete all-3 day×symbol rows | 14 / 14 |
| H^v mean (complete) | 0.48173741550321825 |
| H^v pooled notional | 0.48950294302152425 |
| FEI volume mean | 0.7503412681118782 |
| Vol shares pooled | {'hyperliquid': 0.04048730831061115, 'deribit': 0.3624289872901404, 'kraken': 0.5970837043992484} |
| SSM raw counts | {'hyperliquid': 3075, 'deribit': 349, 'kraken': 244} (total 3668) |
| SSM ≥5bps counts | {'hyperliquid': 486, 'deribit': 60, 'kraken': 43} (total 589) |
| SSM ≥30bps counts | {'hyperliquid': 58, 'deribit': 10, 'kraken': 8} |
| Nanex 30bps counts | {'hyperliquid': 70, 'deribit': 13, 'kraken': 22} |

## Pass 2

| Dig | Result |
|-----|--------|
| Thin-venue excess (5bps) | mean=0.7279863742220212; thin=hyperliquid; spearman(vol,excess)=-1.0 |
| Concord Jaccard@5s | {'hyperliquid_deribit': 0.0, 'hyperliquid_kraken': 0.0, 'deribit_kraken': 0.1255426391790028} |
| Triple frac mean | 0.0 |
| Placebo p(ge obs) mean | 0.5785714285714285 |
| Crossed-book available days | 0; mean frac=None |
| Epps corr@1s day / crash | 0.20209159593171333 / 0.1520719600534684 |
| H^v early / late | 0.4554388321707076 / 0.5080359988357288 |

## Figures

- `figs/fig_herfindahl_shares.png`
- `figs/fig_crash_vs_vol_share.png`
- `figs/fig_concordance_slack.png`
- `figs/fig_epps_day_vs_crash.png`
- `figs/fig_severity_gate.png`

## Decisions

See CANDIDATES. Severity gate is shared in `research.lib.crash.severity_gate` for crash_stats sibling.

## Blockers

- Dense multi-venue TOB on vertical-slice days for crash-window crossed-book (collector often misaligned).  
- Latency/fee haircut before treating any concordance as tradable hedge trigger.  
- Phase 4 hardening: bootstrap CIs on H^v and Jaccard.
