
# Commercial Sector
 The Commercial sector contains all the space heating and cooling for commercial buildings as seen in the NRCAN comprehensive energy use database. 
        
##Commodity
| name      | description                                  | type               | units   |
|:----------|:---------------------------------------------|:-------------------|:--------|
| C\_oil    | (PJ) heating oil in the commercial sector    | annual commodity   | nan     |
| C\_ng     | (PJ) natural gas in the commercial sector    | annual commodity   | nan     |
| C\_elc    | (PJ) electricity (commercial)                | annual commodity   | nan     |
| C\_ng     | (PJ) natural gas in the commercial sector    | annual commodity   | nan     |
| C\_D\_spc | (PJ) demand for commercial space cooling     | demand commodity   | (PJ)    |
| C\_D\_sph | (PJ) demand for commercial space heating     | demand commodity   | (PJ)    |
| C\_D\_oth | (PJ) demand for other commercial energy      | demand commodity   | (PJ)    |
| C\_D\_com | (PJ) commercial energy demand                | demand commodity   | PJ      |

## Technology

| tech                 | description                                                    |   unlim_cap |   annual |   reserve |   curtail |   flex |
|:---------------------|:---------------------------------------------------------------|------------:|---------:|----------:|----------:|-------:|
| C\_SPH\_OIL-EXS      | space heating oil - existing                                   |           0 |        1 |         0 |         0 |      0 |
| C\_SPH\_NG-EXS       | space heating natural gas - existing                           |           0 |        1 |         0 |         0 |      0 |
| C\_SPH\_ELC-EXS      | space heating electric - existing                              |           0 |        1 |         0 |         0 |      0 |
| C\_SPC\_ELC-EXS      | space cooling electric - existing                              |           0 |        1 |         0 |         0 |      0 |
| C\_OTHER             | other all other commercial energy demand                       |           1 |        1 |         0 |         0 |      0 |
| C\_SPHC\_HP\_AIR-NEW | space cooling air-source heat pump typical efficiency - new    |           0 |        1 |         0 |         0 |      0 |
| C\_SPHC\_HP\_GEO-NEW | space cooling geo-exchange heat pump typical efficiency - new  |           0 |        1 |         0 |         0 |      0 |
| C\_SPH\_ELC\_BLR-NEW | space heating electric boiler - new                            |           0 |        1 |         0 |         0 |      0 |
| C\_SPH\_ELC\_RES-NEW | space heating electric resistance heating - new                |           0 |        1 |         0 |         0 |      0 |
| C\_SPH\_NG\_FRN-NEW  | space heating gas furnace - new                                |           0 |        1 |         0 |         0 |      0 |
| C\_SPC\_AC\_ROOF-NEW | space cooling rooftop air-conditioning - new                   |           0 |        1 |         0 |         0 |      0 |
| F\_C\_OIL            | Oil distribution from fuel sector to commercial sector         |           1 |        1 |         0 |         0 |      0 |
| F\_C\_NG             | Natural gas distribution from fuel sector to commercial sector |           1 |        1 |         0 |         0 |      0 |
| E\_C\_ELC            | Electricity distribution to commercial sector                  |           1 |        0 |         0 |         0 |      0 |
| F\_C\_BIO            | bioenergy distribution from fuel sector to commercial sector   |           1 |        1 |         0 |         0 |      0 |
| F\_C\_H2             | Hydrogen distribution from fuel sector to commercial sector    |           1 |        1 |         0 |         0 |      0 |
