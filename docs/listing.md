# Experimental listing name

Joinable (Survival + Overmap Running / true, ports up) is **not** the same as listed. Listed means Funcom accepted `DeclareFarmStatus`.

- **Title** (server browser row): Funcom CR `spec.title`. Set at install from `WorldName`. Admin Settings shows it read-only. Changing it on a live CR can bounce maps.
- **Overlay** (sietch pane after you click the row): `Bgd.ServerDisplayName` in `UserEngine.ini`. Settings → Listing subtitle.

Funcom returns **400 Invalid display name** for some titles and then unlists the world. Overlay strings can show **ACTION REQUIRED … violates guidelines** even when the title is fine. Keep both **short**. Avoid slogan-length rates lists in the title.

If the world vanished from Experimental while other player-run worlds still show:

1. Shorten the title / overlay.
2. Apply UserSettings if you changed the overlay, then restart maps.
3. Watch Gateway: zero recent restarts, no display-name 400s. Admin joinable can still be green while FLS has you unlisted.

House PCs on a **public** IPv4 listing still need `lan-redirect`. That is rubberband, not listing.
