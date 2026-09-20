# Copy to dune-install.config.ps1 and replace every placeholder.
# README.md explains each field. Do not upload or share dune-install.config.ps1.
@{
    WorldName   = "My Sietch"
    # Funcom menu: Asia, Europe, North America, Oceania, South America
    Region      = "North America"
    # Empty = installer picks Ethernet/Wi-Fi. Set only if auto-detect is wrong.
    LanIp       = ""
    # Empty = LAN-only (Funcom lists LanIp). "auto" = look up the current public IPv4
    # at install time for internet players. Need not be a static ISP address.
    AdvertiseIp = ""
    # CasualPve = NoPVP + faster/easier progression (bundled inis)
    # Official  = Funcom depot defaults (PvP/security zones as shipped)
    PlayStyle   = "CasualPve"
    FlsToken    = ""
    Distro      = "Ubuntu"
    WslMemory   = "32GB"
    # Set to the host's logical processor count (do not exceed it).
    WslProcessors = "4"
    WslSwap     = "8GB"
}
