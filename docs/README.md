# Operator notes

These are actions the installer does not do for you. They need a human. Rates and PvP never hot-reload.

Install and daily ops stay in the pack [README](../README.md). The LAN admin is [ADMIN-PANEL.md](../ADMIN-PANEL.md).

| Task | When | Downtime |
| --- | --- | --- |
| [PvP / PvE](pvp.md) | After the world exists | Apply UserSettings + map restart |
| [Listing name](listing.md) | World missing from Experimental, or Funcom “guidelines” overlay | Title change can bounce maps |
| Harvest / durability / XP | Settings tab, or the three inis | Apply UserSettings + map restart |
| Public vs LAN listing | World → Advertise | Maps roll if the IPv4 changes |
| HP3 / could not verify identity | `systemctl is-active dune-fls-dns.service` | No, if the watcher is up |
| House-PC rubberband on a public listing | `lan-redirect` on that PC, not on the host | No |

World **Repair** rebinds join ports. It does not restart maps. World **Restart** kicks everyone.

Do not run `wsl --shutdown` on a live public world.
