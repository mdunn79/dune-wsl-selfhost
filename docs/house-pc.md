# Join from another PC

Play from a **different** computer than the host. Mirrored WSL does not hairpin; joining on the host itself often spins forever.

1. Launch Dune: Awakening (normal Steam install).
2. Server browser → **Experimental** (player-run / self-hosted worlds).
3. Find the name you set as `WorldName`.
4. Connect.

If the tab spins after you click the world, Hagga is usually still starting. On the host, run `Get-DuneStatus.ps1`. Join only when **Survival_1** is `Running` / `true`, not `PostLandscapePhysics`, and not while Gateway is `Modifying`. That can take several minutes after install, and again after a depot update.

**In queue and the world also shows offline.** The listing is still in Funcom’s directory, but Survival is not Ready yet or director TCP `31519` is not bound. Wait until `Get-DuneStatus.ps1` shows both maps Running / true and `31519` listening.

## Public listing (house PCs rubberband)

The Experimental tab lists **one** IPv4 per world. There is no “connect by IP” box. If that IPv4 is your WAN address, a PC in the same house still sends UDP/TCP to the public IP and the router hairpins it back to `LanIp`. Hagga logs the client as your WAN address. Unreal rejects late `ServerMove` packets (about a second old), which feels like rubberbanding. The world can be healthy, CPU idle, and internet players fine. Funcom will not take a LAN address *and* a public one.

**Fix (gaming PC only, not the host):** copy the pack’s `lan-redirect` folder. The host installer writes `lan-redirect\dune-client.config.ps1` with `LanIp` for you. On the house PC:

1. Copy `dune-client.config.example.ps1` to `dune-client.config.ps1` if that file is missing, and set `LanIp` to the host Ethernet/Wi-Fi IPv4.
2. Elevated PowerShell in that folder:
   - One-off, window stays open: `Start-DuneLanRedirect.bat`
   - Hibernate until Dune is running: `Start-DuneLanRedirect.bat watch`
   - Daily, quiet: `Install-DuneLanRedirect.ps1` (logon task). `Install-DuneLanRedirect.ps1 -Service` if the person who plays is not a daily Administrator.
3. If you were already in the world, leave to the server list, then join again after the redirector is up (or after `-WatchDune` has armed).
4. On the **host**, `Get-DuneNetHealth.ps1` (optional `-WatchSeconds 60`). The house PC should show RemoteAddr as `lan` (`192.168.x`), not `hairpin-or-self-wan`. `timestamp_expired_count` in the last 2 minutes should stay near 0 while you move.

Uninstall with `Uninstall-DuneLanRedirect.ps1`. Ports, WinDivert, and Smart App Control: [lan-redirect/README.md](../lan-redirect/README.md). Needs 64-bit PowerShell as Administrator on the gaming PC. Do **not** install it on the Dune host.

Internet friends keep using the public listing. Only house PCs need this helper.

LAN-only listing (`AdvertiseIp` empty): skip `lan-redirect`. The Experimental tab already sends those clients to `LanIp`.
