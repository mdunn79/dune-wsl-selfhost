# Experimental listing name

Joinable (Survival + Overmap Running / true, ports up) is not the same as listed. Listed means Funcom accepted `DeclareFarmStatus`.

- **Title** (server browser row): Funcom CR `spec.title`. Set at install from `WorldName`. Change it on World → Listing → Save title. That patches the live CR and can bounce maps or unlist the world.
- **Overlay** (sietch pane): `Bgd.ServerDisplayName`. Settings → Listing subtitle.

Funcom filters both. A bad **title** returns **400 Invalid display name** and Gateway unlists the world. A bad **overlay** shows **ACTION REQUIRED … Server name violates guidelines** while the title can still list. That is a guidelines reject, not a length cap. A short name can fail; a longer one can pass.

Funcom has not published a self-host character list or length limit. Closest official text: [Dune: Awakening Rules of Conduct](https://cdn.funcom.com/legal/Dune_Rules_of_Conduct.pdf) (names / UGC). This pack also refuses `'` and `|` in `WorldName`. Dashes are allowed.

If the world vanished from Experimental, or the sietch pane shows ACTION REQUIRED:

1. Change the field Funcom flagged (title vs overlay). Do not assume “make it shorter.”
2. Overlay: Apply UserSettings, then restart maps.
3. Gateway: no display-name 400s. Admin joinable can still be green while FLS has you unlisted.

House PCs on a public listing still need `lan-redirect` ([house-pc.md](house-pc.md)). That is rubberband, not listing.
