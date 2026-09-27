# Copy to dune-client.config.ps1 on the GAMING PC (or let the host installer write it).
# LanIp = Dune host Ethernet/Wi-Fi IPv4, not this PC and not 127.0.0.1.
@{
    LanIp     = "192.168.1.101"
    PublicIp  = "auto"
    # Optional. Used with -WatchDune / the logon task.
    # DuneProcessNames = @("DuneSandbox-Win64-Shipping", "DuneAwakening")
}
