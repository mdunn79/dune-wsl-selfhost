# Operator notes

The installer does not do these. Rates and PvP never hot-reload.

First install stays in the pack [README](../README.md). The LAN admin is [ADMIN-PANEL.md](../ADMIN-PANEL.md).

| Task | When | Downtime |
| --- | --- | --- |
| [PvP / PvE](pvp.md) | After the world exists | Apply UserSettings + map restart |
| [Listing name](listing.md) | World missing from Experimental, or Funcom “guidelines” overlay | Title change can bounce maps |
| Harvest / durability / XP | Settings tab, or the three inis | Apply UserSettings + map restart |
| Public vs LAN listing | World → Advertise | Maps roll if the IPv4 changes |
| [Join from another PC](house-pc.md) | Experimental tab, not the host. Public listing: `lan-redirect` on house PCs | No |
| [Keep it running](maintain.md) | Hourly Steam/check, 5-minute join ports. Unattended reboot: autologon as the task user. Leave the Dune battlegroup window open | Only if a depot or advertise IP actually changed |
| [After it is up](troubleshoot.md) | Queue, HP3, timeout, hitch, world Stopped | Depends |

World **Repair** rebinds join ports. It does not restart maps. World **Restart** kicks everyone.

Do not run `wsl --shutdown` on a live public world.
