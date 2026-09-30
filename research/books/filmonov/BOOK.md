# Filimonov — HFT Technology, Strategies, Regulations

| Field | Value |
|-------|-------|
| **Author** | Vladimir Filimonov |
| **Title** | *High-Frequency Trading. Technology, Strategies, Regulations* |
| **Edition / provenance** | Slides, **Perm Winter School 2013** (43 pp). Local PDF: [`Filimonov.pdf`](Filimonov.pdf) (gitignored `*.pdf`). |
| **Slug** | `filmonov` |

Book PDF and verbatim extracts under `_raw/` stay **local-only** (gitignored via repo `research/books/**/_raw/` + `*.pdf`). Do not commit copyrighted text.

**Not** Filimonov–Sornette Hawkes / branching-ratio work (that lineage lives under [`../mmip/`](../mmip/)). This program owns a **named abuse/latency detector catalog** from the 2013 keynote: stuffing, fade, ignition, smoking/layering, clock hunting, plus MM latency/size context.

This tree mirrors [`../mm_confr_viewpoints/`](../mm_confr_viewpoints/) (single-talk slide program): chapter packages, experiment scripts, notebooks, and `out/` artifacts. Shared lib: [`../../lib/hftpat.py`](../../lib/hftpat.py). Quality bar: [`../../LOOP.md`](../../LOOP.md). Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md).

**Core claim (deck → crypto test):** public-tape fingerprints of quote stuffing, post-trade book fade (same-venue and cross-venue), momentum ignition (3-phase volume→move→reversion), smoking/spoof proxies, clock-aligned fill clusters, and venue OTR/size-latency regimes are desk-usable as **monitor / exec throttle / risk-policy** objects — not α by default.

**Hard distinctions (do not re-Promote):**
- [`../../lib/crash.py`](../../lib/crash.py) Nanex/SSM / V-recovery ≠ ignition’s **3-phase** fingerprint
- [`../../lib/vstat.py`](../../lib/vstat.py) MinV ≠ ignition cause sequence
- [`../../lib/lob.py`](../../lib/lob.py) `tob_depletion_cancel_proxy` / refill ≠ **post-trade conditional price/venue fade**
- Cross-link only; new objects live in `hftpat.py`

**Venue set (locked):** Hyperliquid + Deribit + **Kraken** core.

**Lenses:** `risk` · `info` · `exec` · `disc` · `cont` · `liq` · `mm`

**Two-pass protocol (mandatory):** every package ships Pass 1 (faithful deck object on HL+Deribit+Kraken) then Pass 2 (info/signals dig + falsifiers + overlap gates) before Promote/Hold/Kill. See [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md).

**Program status:** Hardened — **0 Promote / 21 Hold / 11 Kill**. Desk: [`DESK_MEMO.md`](DESK_MEMO.md) · Index: [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md).

**Out of scope:** Filimonov–Sornette Hawkes MLE; production firm-ID spoof prosecution; Reg NMS flash-order replication; `applications/` playbooks until Promote-as-risk-policy freezes.
