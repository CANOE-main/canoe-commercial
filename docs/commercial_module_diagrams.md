# canoe-commercial: Module Diagrams

---

## 1. Overall Module Pipeline

Data flows left-to-right from external sources through the module's processing steps to the TEMOA database tables that downstream optimization reads.

```mermaid
flowchart LR
    subgraph EXT["External Sources"]
        NRCAN["NRCan CEUD\nTables 1 · 24 · 32\nBase-year secondary energy\nby end-use & fuel"]
        AEO["EIA AEO CDM 2023\nktekx.xlsx\nUS installed-base market shares\nefficiencies · costs · lifetimes"]
        COMSTOCK["NREL ComStock 2024\n14 commercial building types\nhourly load profiles\nper US state"]
        RNINJA["Renewables Ninja\nHourly temperature &\nhumidity (2018)\nCA provinces · US states"]
        STATCAN["StatCan\n25-10-0029: Atlantic energy shares\n17-10-0009/0057: Population\nhistorical & projected"]
        CER["CER Energy Futures 2023\nProvincial GDP projections\nGlobal Net-zero scenario"]
    end

    subgraph PROC["Processing"]
        WMAP["Weather Mapping\nBuild 8760×8760 matrix\nmatching each CA hour to\nUS hours by temp ±1°C & humidity"]
        DSD_C["DSD Calculation\nSum ComStock building types\nApply weather map to climate-\nsensitive end uses · Normalize"]
        EXS_C["Existing Stock Estimation\nNRCan SEC × AEO avg-EFF → DEM\nComStock DSD → ACF = mean/max\nDEM ÷ ACF → CAP\nSpread CAP across vintage years"]
        PROJ["Demand Projection\nBase-year DEM × GDP index(t)\nby province & period"]
        NEW_C["New Technology Data\nAEO CDM tech-menu entries\nfor each candidate technology"]
    end

    subgraph DB["TEMOA Database Outputs"]
        D_OUT["Demand\nAnnual energy service\nPJ by region & period"]
        DSD_OUT["DemandSpecificDistribution\nNormalized 8760-hr shape\nper demand commodity & region"]
        ECAP["ExistingCapacity\nVintaged installed stock\nby technology & region"]
        EFF["Efficiency\nFuel → service conversion\nper tech · vintage · region"]
        COSTS["CostInvest / CostFixed\nCapital & O&M costs\nper tech · vintage · period"]
        LIMITS["LimitAnnualCapacityFactor\nACF upper bound per tech\n\nLimitTechInputSplitAnnual\nFuel-mix shares for other"]
    end

    NRCAN -->|"secondary energy\nby fuel & end-use"| EXS_C
    NRCAN -->|"base-year totals"| PROJ
    STATCAN -->|"Atlantic province\ndisaggregation"| EXS_C
    STATCAN -->|"population\nprojections"| PROJ
    CER -->|"GDP index by province"| PROJ
    AEO -->|"market shares\nefficiencies · costs · lifetimes"| EXS_C
    AEO -->|"new tech specs"| NEW_C
    COMSTOCK -->|"hourly building\nload profiles"| DSD_C
    RNINJA -->|"CA & US\nhourly climate data"| WMAP
    WMAP -->|"climate-adjusted\nprofile weights"| DSD_C

    DSD_C -->|"normalized profiles"| DSD_OUT
    DSD_C -->|"ACF = mean / max"| LIMITS
    PROJ --> D_OUT
    EXS_C --> ECAP
    EXS_C --> EFF
    EXS_C --> COSTS
    NEW_C --> EFF
    NEW_C --> COSTS
    EXS_C -->|"fuel-mix shares"| LIMITS
```

---

## 2. Energy System Structure

The commodity-technology-demand network as TEMOA sees it. Fuel commodities (left) are converted by end-use technologies (centre) into energy services that must meet the imposed demands (right). Existing and new technologies are distinguished; distribution techs bridge from upstream supply modules.

```mermaid
flowchart LR
    subgraph SUPPLY["Upstream supply\n(other CANOE modules)"]
        direction TB
        UP_NG["Natural gas\n(canoe-fuel)"]
        UP_OIL["Heating oil\n(canoe-fuel)"]
        UP_ELC["Electricity\n(canoe-electricity)"]
        UP_BIO["Bioenergy\n(canoe-fuel)"]
        UP_H2["Hydrogen\n(canoe-fuel)"]
    end

    subgraph DIST["Distribution bridge"]
        direction TB
        F_NG["F_C_NG"]
        F_OIL["F_C_OIL"]
        E_ELC["E_C_ELC"]
        F_BIO["F_C_BIO"]
        F_H2["F_C_H2"]
    end

    subgraph COMM["Commercial fuel\ncommodities"]
        direction TB
        C_NG["C_NG\nNatural gas"]
        C_OIL["C_OIL\nHeating oil"]
        C_ELC["C_ELC\nElectricity"]
        C_BIO["C_BIO\nBioenergy"]
        C_H2["C_H2\nHydrogen"]
    end

    subgraph TECH_SPH["Space Heating Technologies"]
        direction TB
        subgraph EXS_SPH["Existing stock"]
            SPH_OIL_E["C_SPH_OIL-EXS\nOil heating"]
            SPH_NG_E["C_SPH_NG-EXS\nGas heating"]
            SPH_ELC_E["C_SPH_ELC-EXS\nElectric heating"]
        end
        subgraph NEW_SPH["New capacity"]
            HP_AIR["C_SPHC_HP_AIR-NEW\nAir-source heat pump"]
            HP_GEO["C_SPHC_HP_GEO-NEW\nGeo-exchange heat pump"]
            ELC_BLR["C_SPH_ELC_BLR-NEW\nElectric boiler"]
            ELC_RES["C_SPH_ELC_RES-NEW\nElectric resistance"]
            NG_FRN["C_SPH_NG_FRN-NEW\nGas furnace"]
        end
    end

    subgraph TECH_SPC["Space Cooling Technologies"]
        direction TB
        subgraph EXS_SPC["Existing stock"]
            SPC_ELC_E["C_SPC_ELC-EXS\nElectric cooling"]
        end
        subgraph NEW_SPC["New capacity"]
            AC_ROOF["C_SPC_AC_ROOF-NEW\nRooftop AC"]
        end
    end

    subgraph TECH_OTH["Other End Uses"]
        C_OTHER["C_OTHER\nCatch-all dummy tech\nunlimited capacity · EFF = 1\nfuel mix constrained by TIS"]
    end

    subgraph DEMANDS["Demand Commodities"]
        direction TB
        D_SPH["C_D_sph\nSpace Heating\nDemand (PJ)"]
        D_SPC["C_D_spc\nSpace Cooling\nDemand (PJ)"]
        D_OTH["C_D_oth\nOther Commercial\nDemand (PJ)"]
    end

    UP_NG --> F_NG --> C_NG
    UP_OIL --> F_OIL --> C_OIL
    UP_ELC --> E_ELC --> C_ELC
    UP_BIO --> F_BIO --> C_BIO
    UP_H2 --> F_H2 --> C_H2

    C_OIL --> SPH_OIL_E --> D_SPH
    C_NG --> SPH_NG_E --> D_SPH
    C_ELC --> SPH_ELC_E --> D_SPH
    C_ELC --> HP_AIR --> D_SPH
    C_ELC --> HP_GEO --> D_SPH
    C_ELC --> ELC_BLR --> D_SPH
    C_ELC --> ELC_RES --> D_SPH
    C_NG --> NG_FRN --> D_SPH

    C_ELC --> SPC_ELC_E --> D_SPC
    C_ELC --> HP_AIR --> D_SPC
    C_ELC --> HP_GEO --> D_SPC
    C_ELC --> AC_ROOF --> D_SPC

    C_NG & C_OIL & C_ELC --> C_OTHER --> D_OTH
```

---

## 3. Existing Stock Calculation

The module cannot directly observe what equipment is installed in Canadian commercial buildings. It reconstructs existing capacity by combining Canadian energy consumption data (NRCan) with US market-share and efficiency data (AEO CDM). The chain below is applied independently for each `(region, end-use, fuel)` combination.

```mermaid
flowchart TD
    subgraph STEP1["Step 1 — Base-year secondary energy (NRCan)"]
        NRCAN_T24["NRCan Table 24\nSpace heating SEC by fuel"]
        NRCAN_T32["NRCan Table 32\nSpace cooling SEC by fuel"]
        ATL{"Atlantic\nprovince?"}
        STATCAN_ATL["StatCan 25-10-0029\nProvincial energy shares\nfor NB · NS · PEI · NL"]
        SEC["SEC\nbase-year secondary energy\nby end-use & fuel (PJ in)"]

        NRCAN_T24 --> ATL
        NRCAN_T32 --> ATL
        ATL -->|"Yes — NRCan\naggregates Atlantic"| STATCAN_ATL
        STATCAN_ATL -->|"fraction per province"| SEC
        ATL -->|"No"| SEC
    end

    subgraph STEP2["Step 2 — Average efficiency of installed stock (AEO CDM)"]
        AEO_SHARES["AEO CDM installed base\nService-energy market shares\nby (census division, end-use, fuel, tech)"]
        SEC_SHARES["Convert to secondary-energy shares\nsec_share_i = serv_share_i ÷ eff_i\nnormalized per (end-use, fuel)"]
        AVG["Weighted averages\nEFF = Σ(eff_i × sec_share_i)\nLIFE = Σ(life_i × serv_share_i)\nOM_COST = Σ(om_i × serv_share_i)"]

        AEO_SHARES --> SEC_SHARES --> AVG
    end

    subgraph STEP3["Step 3 — Service demand"]
        DEM["DEM (base year)\n= SEC × EFF\n(PJ of useful output)"]
        CER_GDP["CER GDP projections\nGlobal Net-zero"]
        GDP_IDX["GDP index\nnormalized to base year"]
        DEM_T["DEM(period t)\n= DEM(base) × GDP_index(t)"]

        DEM --> DEM_T
        CER_GDP --> GDP_IDX --> DEM_T
    end

    subgraph STEP4["Step 4 — Annual capacity factor (from DSD)"]
        DSD["Normalized hourly demand profile\nDSD[h] for this end-use & region\n(see Diagram 4)"]
        ACF["ACF = mean(DSD) / max(DSD)\nUpper bound: tech cannot run\nflatter than demand is peaked"]

        DSD --> ACF
    end

    subgraph STEP5["Step 5 — Existing capacity & vintage spread"]
        C2A["C2A = 1\n(capacity in PJ/y,\nactivity in PJ)"]
        CAP["CAP (total)\n= DEM ÷ ACF\n(PJ/y of rated capacity)"]
        VINTS["Spread uniformly across vintages\nbase_year − LIFE … base_year\nCAP[v] = (1/LIFE) × CAP_total"]
        PRUNE["Drop vintage v if\nv + LIFE ≤ first model period\n(already fully retired)"]

        C2A --> CAP
        CAP --> VINTS --> PRUNE
    end

    subgraph OUT["Database rows written per surviving vintage"]
        direction LR
        EC["ExistingCapacity\n(region, tech, vintage, capacity)"]
        EF["Efficiency\n(region, input_comm, tech, vintage,\noutput_comm, efficiency=EFF)"]
        LT["LifetimeTech\n(region, tech, lifetime=LIFE)"]
        CF["CostFixed\n(region, period, tech, vintage,\ncost=OM_COST)"]
        ACF_LIM["LimitAnnualCapacityFactor\n(region, tech, factor=ACF, op=le)"]
    end

    SEC --> DEM
    AVG --> DEM
    AVG --> ACF_LIM
    PRUNE --> EC
    AVG --> EF
    AVG --> LT
    AVG --> CF
    ACF --> ACF_LIM
```

---

## 4. Within-Year Demand Shaping (DSD Derivation)

TEMOA requires a normalized hourly demand profile (DemandSpecificDistribution) to know *when* within the year each demand must be met. Because no Canadian equivalent of ComStock exists, profiles are derived from US building data re-mapped to Canadian climate conditions.

```mermaid
flowchart TD
    subgraph WEATHER_STEP["Climate Mapping — done once per province"]
        RNINJA_CA["Renewables Ninja\nCA province: hourly\ntemperature & humidity (2018)"]
        RNINJA_US["Renewables Ninja\nAnalog US state: hourly\ntemperature & humidity (2018)"]
        MAP_BUILD["Build 8760×8760 mapping matrix\nFor each of 8760 CA hours:\n  find US hours with\n  same humidity & temp ±1°C\n  weight = 1 / n_matches\nFallback: coldest/hottest US hour"]
        MAP_CACHE["Cache matrix to disk\n(compressed .npz)\nReused on subsequent runs"]

        RNINJA_CA --> MAP_BUILD
        RNINJA_US --> MAP_BUILD
        MAP_BUILD --> MAP_CACHE
    end

    subgraph COMSTOCK_STEP["ComStock Data — per province × building type"]
        COMSTOCK_DL["Download hourly load CSV\nper building type per US state\n(14 building types)"]
        ALIGN["Align timezone to EST\nRoll to 00:00 Jan 1 start\nKeep hourly rows only"]
        SUM_BUILD["Sum across all 14\nbuilding types by column\n(end-use × fuel combinations)"]
        MAP_COLS["Map ComStock columns\nto module end-uses\n(space heating · cooling · other)"]

        COMSTOCK_DL --> ALIGN --> SUM_BUILD --> MAP_COLS
    end

    subgraph APPLY_MAP["Apply Weather Map — per end-use"]
        CLIMATE_SENS{"Climate-sensitive\nend use?"}
        APPLY["CA profile =\nmatrix × US profile\n(matrix multiply)\nInterpolate any NaN hours"]
        CLIP["Clip negative values to 0\n(occurs for very cold CA hours\nwith no US analog)"]
        NO_MAP["Use US profile directly\n(lighting, plug loads:\noutdoor climate-independent)"]

        CLIMATE_SENS -->|"space heating\nspace cooling"| APPLY --> CLIP
        CLIMATE_SENS -->|"other end uses"| NO_MAP
    end

    subgraph NORMALIZE["Normalize — per end-use & region"]
        AGG["Sum component profiles\ninto end-use aggregate\n(e.g. SPH_NG + SPH_OIL + SPH_ELC → space heating)"]
        NORM["Normalize:\nDSD[h] = profile[h] / Σ profile\n→ sums to 1.0 over 8760 hours"]
        ACF_DERIVE["ACF = mean(DSD) / max(DSD)\n(capacity factor upper bound\nfor optimizer)"]
        TOL["Apply dsd_tolerance filter:\nset DSD[h] = 0 if < 0.02 × mean\n(remove near-zero hours\nfor computational efficiency)"]

        AGG --> NORM --> TOL
        NORM --> ACF_DERIVE
    end

    subgraph OUT["Database rows written"]
        DSD_ROW["DemandSpecificDistribution\n(region, period, season, tod,\ndemand_name, dsd)\n8760 rows × n_periods × n_regions"]
        ACF_ROW["LimitAnnualCapacityFactor\n(region, tech, factor=ACF, op=le)\nOne row per tech & period"]
    end

    MAP_CACHE --> APPLY
    MAP_COLS --> CLIMATE_SENS
    CLIP --> AGG
    NO_MAP --> AGG
    TOL --> DSD_ROW
    ACF_DERIVE --> ACF_ROW
```

---

## 5. "Other" End Uses — Treatment and Electrification Trajectory

All commercial energy consumption that is not space heating or space cooling (lighting, water heating, refrigeration, cooking, plug loads, etc.) is modelled as a single catch-all commodity served by a single unlimited-capacity technology. The optimizer has no technology choice here; instead, the fuel mix is constrained exogenously by a parameterized electrification trajectory.

```mermaid
flowchart TD
    subgraph DATA["Base-year data"]
        NRCAN_T1["NRCan Table 1\nTotal commercial SEC by fuel"]
        SPHC_SEC["Space heating & cooling\nSEC by fuel\n(already modelled explicitly)"]
        OTH_SEC["Other SEC by fuel\n= Total − SPHC\n(residual)"]

        NRCAN_T1 --> OTH_SEC
        SPHC_SEC --> OTH_SEC
    end

    subgraph TECH["Technology definition"]
        DUMMY["C_OTHER\nDummy technology\nunlimited capacity · annual flag\nEfficiency = 1 (SEC = DEM)\n\nOne vintage: first model period\nNo capital cost · No lifetime limit"]
        D_OTH["C_D_oth\nOther commercial demand\ncommodity (PJ)"]
        FUELS["All input fuels linked\nvia separate Efficiency rows:\nC_NG · C_OIL · C_ELC · ...\neach with efficiency = 1"]

        DUMMY --> D_OTH
        FUELS --> DUMMY
    end

    subgraph DEMAND_PROJ["Demand projection"]
        OTH_DEM["Base-year DEM\n= Σ(SEC over all fuels)"]
        GDP_IDX["GDP index by period"]
        DEM_T["DEM(t) = DEM_base × GDP_index(t)"]
        DSD_OTH["DSD for 'other'\n= ComStock profiles for\nlighting & equipment\n(no weather mapping)"]

        OTH_DEM --> DEM_T
        GDP_IDX --> DEM_T
    end

    subgraph ELEC["Electrification trajectory (LimitTechInputSplitAnnual)"]
        BASE_SHARES["Base shares:\nTIS_fuel(base) = SEC_fuel / Σ SEC"]
        CEF["Electrification factor: 62%\n(CER 2023 — 62% of non-electric\nfuel consumption replaced 1:1\nby electricity by 2050)"]
        LINEAR["Linear interpolation\nlin_f = (t − base_year) / (2050 − base_year)\n\nElectricity:  target = 0.62 + TIS_elc × 0.38\nOther fuels:  target = TIS_fuel × 0.38\n\nTIS(t) = TIS_base + (target − TIS_base) × lin_f"]
        CONSTRAINT["LimitTechInputSplitAnnual\noperator = 'le'\nProportion = TIS(t)\nper (region, period, fuel)"]

        BASE_SHARES --> LINEAR
        CEF --> LINEAR
        LINEAR --> CONSTRAINT
    end

    subgraph OUT["Database rows written"]
        D_ROW["Demand\n(region, period, C_D_oth, PJ)"]
        DSD_ROW["DemandSpecificDistribution\n(region, period, season, tod,\nC_D_oth, dsd)"]
        TIS_ROW["LimitTechInputSplitAnnual\n(region, period, fuel, tech=C_OTHER,\nproportion=TIS(t), op=le)"]
    end

    OTH_SEC --> BASE_SHARES
    OTH_SEC --> OTH_DEM
    DEM_T --> D_ROW
    DSD_OTH --> DSD_ROW
    CONSTRAINT --> TIS_ROW
```
