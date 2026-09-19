# Copy to dune-install.config.ps1 and replace every placeholder with your values.
# README.md explains each field. Keep dune-install.config.ps1 on this PC only.
@{
    WorldName   = "My Sietch"
    # Funcom menu: Asia, Europe, North America, Oceania, South America
    Region      = "North America"
    LanIp       = "192.168.0.10"
    # Empty = LAN-only (clients use LanIp). For internet players, your public WAN IPv4.
    AdvertiseIp = ""
    # CasualPve = NoPVP + faster/easier progression (bundled inis)
    # Official  = Funcom depot defaults (PvP/security zones as shipped)
    PlayStyle   = "CasualPve"
    FlsToken    = ""
    Distro      = "Ubuntu"
    WslMemory   = "32GB"
    WslProcessors = "8"
    WslSwap     = "8GB"
}
