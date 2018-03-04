# TG-1 and TG-789 modem statistics

Fetches statistics from a tgiinet modem. These are made by Technicolor, 
sold by Australian ISP iinet. 

I've tested with 15.4 firmware (15.53.7004-V1-7-1-CRF557) in bridge mode.
Thanks to Shannon Wynter for his [nbntest](https://github.com/freman/nbntest/), some
details were found there.

Edit `tgiistat.toml` to set your modem's IP and password.

This requires python3.

## Install
```
python3 -m venv init venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

## Usage

```
./venv/bin/python3 tgiistat.py
up_rate 1010
down_rate 4850
up_maxrate 1020
down_maxrate 5480
up_power 17.1
down_power 12.4
up_noisemargin 10.9
down_noisemargin 11.3
up_transferred 193.51
down_transferred 650.39
up_attenuation1 19.3
down_attenuation1 36.0
dsl_uptime 19565
dsl_mode Interleaved
dsl_type ADSL2+
dsl_status Up

```

```
./venv/bin/python3 tgiistat.py  --json
{
    "up_rate": 1010,
    "down_rate": 4850,
    "up_maxrate": 1020,
    "down_maxrate": 5480,
    "up_power": 17.1,
    "down_power": 12.4,
    "up_noisemargin": 10.9,
    "down_noisemargin": 11.3,
    "up_transferred": 193.51,
    "down_transferred": 650.39,
    "up_attenuation1": 19.3,
    "down_attenuation1": 36.0,
    "dsl_uptime": 19565,
    "dsl_mode": "Interleaved",
    "dsl_type": "ADSL2+",
    "dsl_status": "Up"
}
```
