# X-venue lag taker

Primary (`TI-xvenue-lag:hl_to_thick`): **Kill** — net PnL CI entirely ≤0 after costs (mean=-4.17)

| rule | decision |
|------|----------|
| TI-xvenue-lag:all_pairs | **Kill** |
| TI-xvenue-lag:hl_to_thick | **Kill** |
| TI-xvenue-lag:any_to_thick | **Kill** |
| TI-xvenue-lag:hl_nest_to_thick | **Kill** |
| TI-xvenue-lag:hl_intensity2_thick | **Kill** |

```bash
cd research/books/cross_miniflash/applications/edge_lab/xvenue_lag
python3 exp_xvenue_lag.py
```
