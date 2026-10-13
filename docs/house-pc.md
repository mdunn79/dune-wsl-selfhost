# Join from another PC

Play from a different computer than the host. Mirrored WSL does not hairpin; joining on the host often spins forever.

1. Launch Dune: Awakening (normal Steam client).
2. Server browser → **Experimental**.
3. Find the `WorldName`.
4. Connect.

If the tab spins after you click the world, Hagga is usually still starting. On the host, `Get-DuneStatus.ps1`. Join when **Survival_1** is `Running` / `true`, not `PostLandscapePhysics`, and Gateway is not `Modifying`. That can take several minutes after install or a depot update.

**In queue and the world also shows offline.** The listing is still in Funcom’s directory, but Survival is not Ready or director TCP `31519` is not bound. Wait until both maps are Running / true and `31519` is listening.

## Public listing (house PCs rubberband)

Experimental lists one IPv4. If that is the WAN address, a house PC hairpins through the router. Hagga sees the WAN IP. Late `ServerMove` packets feel like rubberband. Internet friends can be fine. Funcom will not take a LAN address and a public one.

**Fix on the gaming PC only, not the host.** Copy the pack `lan-redirect` folder. The host installer writes `lan-redirect\dune-client.config.ps1` with `LanIp`.

1. If that file is missing, copy `dune-client.config.example.ps1` to `dune-client.config.ps1` and set `LanIp` to the host Ethernet/Wi-Fi IPv4.
2. Elevated PowerShell in that folder:
   - One-off: `Start-DuneLanRedirect.bat`
   - Hibernate until Dune is running: `Start-DuneLanRedirect.bat watch`
   - Daily: `Install-DuneLanRedirect.ps1`. Use `-Service` if the player is not a daily Administrator.
3. Leave to the server list, then join again after the redirector is up.
4. On the **host**, `Get-DuneNetHealth.ps1`. The house PC should show RemoteAddr as `lan` (`192.168.x`), not `hairpin-or-self-wan`. `timestamp_expired_count` should stay near 0 while you move.

Uninstall: `Uninstall-DuneLanRedirect.ps1`. Ports and WinDivert: [lan-redirect/README.md](../lan-redirect/README.md). Do not install it on the Dune host.

Internet friends keep using the public listing. LAN-only (`AdvertiseIp` empty): skip `lan-redirect`.
