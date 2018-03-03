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
python -m venv init venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

## Usage

```
./venv/bin/python tgiistat.py
down_rate 4.73
up_rate 1.02
down_power 12.4
up_power 17.3
down_attenuation0 33.0
up_attenuation0 19.4
down_noisemargin 10.9
up_noisemargin 10.4
```

```
./venv/bin/python tgiistat.py  --json
{
    "down_rate": 4.73,
    "up_rate": 1.02,
    "down_power": 12.4,
    "up_power": 17.3,
    "down_attenuation0": 33.0,
    "up_attenuation0": 19.4
    "down_noisemargin": 10.8,
    "up_noisemargin": 10.5,
}
```
