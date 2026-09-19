# Copy to dune-install.config.ps1 and fill in FlsToken.
# Do not commit dune-install.config.ps1 (it holds the Funcom JWT).
# The installer does not prompt for world name, region, or IP — those come from here.
@{
    WorldName   = "My Sietch"
    # Funcom menu: Asia, Europe, North America, Oceania, South America
    Region      = "North America"
    LanIp       = "192.168.0.10"
    # CasualPve = NoPVP + faster/easier progression (bundled inis)
    # Official  = Funcom depot defaults (PvP/security zones as shipped)
    PlayStyle   = "CasualPve"
    FlsToken    = ""
    Distro      = "Ubuntu"
    WslMemory   = "32GB"
    WslProcessors = "8"
    WslSwap     = "8GB"
}
