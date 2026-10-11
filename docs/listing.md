# Experimental listing name

Joinable (Survival + Overmap Running / true, ports up) is **not** the same as listed. Listed means Funcom accepted `DeclareFarmStatus`.

- **Title** (server browser row): Funcom CR `spec.title`. Set at install from `WorldName`. Admin Settings shows it read-only. Changing it on a live CR can bounce maps.
- **Overlay** (sietch pane after you click the row): `Bgd.ServerDisplayName` in `UserEngine.ini`. Settings → Listing subtitle.

Funcom filters both strings. A title can fail with **400 Invalid display name**; Gateway then unlists the world (`DeclareBattlegroupShutdown`). An overlay can fail with **ACTION REQUIRED … Server name violates guidelines** while the title still shows in Experimental. Those are separate fields. The overlay message is a guidelines reject, not a length cap. A short name can fail; a longer one can pass.

Funcom has **not** published a self-host listing-name character list or length limit. The self-host setup page does not document DisplayName rules. The closest official text is the [Dune: Awakening Rules of Conduct](https://cdn.funcom.com/legal/Dune_Rules_of_Conduct.pdf): names (and other UGC) must not be what Funcom determines is inappropriate, abusive, hateful, harassing, profane, defamatory, threatening, obscene, sexually explicit, infringing, privacy-invasive, vulgar, offensive, indecent, or unlawful. This pack’s installer also refuses `'` and `|` in `WorldName`. That is not Funcom’s full filter. Community claims that dashes are banned are false (titles with `-` list).

If the world vanished from Experimental while other player-run worlds still show, or the sietch pane shows ACTION REQUIRED:

1. Change the string Funcom flagged (title vs overlay). Treat the in-game guidelines line as the reason. Do not assume “make it shorter.”
2. Apply UserSettings if you changed the overlay, then restart maps.
3. Watch Gateway: zero recent restarts, no display-name 400s. Admin joinable can still be green while FLS has you unlisted.

House PCs on a **public** IPv4 listing still need `lan-redirect`. That is rubberband, not listing: [house-pc.md](house-pc.md).
