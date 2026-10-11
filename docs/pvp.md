# PvP and PvE

`PlayStyle` is only read at **first world create**. After that, change the live inis.

This pack’s Funcom maps: partition **1** Hagga, **2** Overmap, **3** Arrakeen, **4** Harko, **8** Deep Desert. There is **one** Deep Desert. Official dual PvE/PvP DD instances are not in this template.

Always:

- Empty the world (or accept a kick).
- Keep `m_bShouldForceEnablePvpOnAllPartitions=False` unless you want Hagga and the cities on PvP too.
- Keep `m_bAreSecurityZonesEnabled=True` unless you want abilities/PvP inside hubs.
- Write **both** File Browser `/srv/UserSettings` and `setup/config`. Admin Settings → Save does both.
- **Apply UserSettings**, then **Restart** maps. Skipping either leaves the old rules loaded.

## PvE (pack CasualPve)

`UserServerCustomSettings.ini`:

```
PVPMode=NoPVP
```

`UserGame.ini`:

```
m_bShouldForceEnablePvpOnAllPartitions=False
m_bAreSecurityZonesEnabled=True
```

Leave `+m_PvpEnabledPartitions=` lines commented.

## Deep Desert PvP, Hagga/cities PvE

Not proven identical to Funcom’s official row. Closest this template allows:

`UserServerCustomSettings.ini`:

```
PVPMode=Limited
```

`UserGame.ini`:

```
m_bShouldForceEnablePvpOnAllPartitions=False
+m_PvpEnabledPartitions=8
m_bAreSecurityZonesEnabled=True
```

Do not add partitions 1, 3, or 4. `Limited` is Funcom’s old Hagga-wreck flag, not “DD only”. Partition 8 is what actually opens Deep Desert.

`FullPVP` is everywhere.

## Where to edit

1. LAN admin → Settings → PvP, Save, Apply UserSettings, Restart (Dry-run off).
2. Or edit this folder’s inis, copy over `/home/dune/.dune/download/scripts/setup/config/`, then:

```powershell
wsl -d Ubuntu -u dune -- /home/dune/.dune/bin/battlegroup apply-default-usersettings
wsl -d Ubuntu -u dune -- /home/dune/.dune/bin/battlegroup restart
```

Do not commit live PvP values back into this pack. The bundled inis stay CasualPve / NoPVP.
