"""Static branch catalog verified against the chains' public directories.

This is the MVP replacement for a cinema database. Provider IDs belong here,
not in adapters, so a branch can be added or disabled in one place. Branch
names and provider IDs come from the chains' public directories; locations are
static application data and should be reviewed whenever a provider changes.
"""

from dataclasses import dataclass

from app.models.cinema import Cinema


@dataclass(frozen=True)
class CinemaConfig:
    cinema: Cinema
    schedule_id: str | int | None = None
    seat_site_id: int | None = None


def _cinema(
    id: str, chain: str, name: str, address: str, latitude: float, longitude: float,
    *, schedule_id: str | int | None = None, seat_site_id: int | None = None,
    schedule_supported: bool = False, seats_supported: bool = False,
) -> CinemaConfig:
    return CinemaConfig(
        cinema=Cinema(
            id=id, chain=chain, name=name, address=address,
            latitude=latitude, longitude=longitude,
            schedule_supported=schedule_supported, seats_supported=seats_supported,
        ),
        schedule_id=schedule_id,
        seat_site_id=seat_site_id,
    )


# Cinema City changed its public schedule site in October 2026. The listed
# branches are current, but schedule support remains disabled until its new
# schedule API is normalized.
CINEMA_CATALOG: tuple[CinemaConfig, ...] = (
    _cinema("cinema-city-glilot", "cinema_city", "Cinema City Glilot", "Glilot Junction, Ramat Hasharon", 32.146658, 34.804708, schedule_id=1170, seats_supported=True),
    _cinema("cinema-city-rishon-lezion", "cinema_city", "Cinema City Rishon LeZion", "Rishon LeZion", 31.983831, 34.769975),
    _cinema("cinema-city-jerusalem", "cinema_city", "Cinema City Jerusalem", "Yitzhak Rabin Boulevard, Jerusalem", 31.782675, 35.203903),
    _cinema("cinema-city-kfar-saba", "cinema_city", "Cinema City Kfar Saba", "Kfar Saba", 32.175000, 34.907000),
    _cinema("cinema-city-netanya", "cinema_city", "Cinema City Netanya", "Netanya", 32.291251, 34.862056),
    _cinema("cinema-city-hadera", "cinema_city", "Cinema City Hadera", "Hadera", 32.434000, 34.919000),
    _cinema("cinema-city-beer-sheva", "cinema_city", "Cinema City Beer Sheva", "Beer Sheva", 31.234178, 34.799308),
    _cinema("cinema-city-ashdod", "cinema_city", "Cinema City Ashdod", "Ashdod", 31.792870, 34.639148),

    _cinema("yes-planet-ayalon", "yes_planet", "Planet Ayalon", "Ayalon Mall, Abba Hillel Silver 301, Ramat Gan", 32.100334, 34.826633, schedule_id="1025", schedule_supported=True, seats_supported=True),
    _cinema("yes-planet-beer-sheva", "yes_planet", "Planet Beer Sheva", "Baruch Katinka 2, Beer Sheva", 31.224420, 34.801440, schedule_id="1074", schedule_supported=True, seats_supported=True),
    _cinema("yes-planet-zichron-yaakov", "yes_planet", "Planet Zichron Yaakov", "M Mall Zichron Yaakov", 32.569260, 34.933388, schedule_id="1075", schedule_supported=True, seats_supported=True),
    _cinema("yes-planet-haifa", "yes_planet", "Planet Haifa", "Cinemall, HaHistadrut 55, Haifa", 32.793670, 35.038270, schedule_id="1070", schedule_supported=True, seats_supported=True),
    _cinema("yes-planet-jerusalem", "yes_planet", "Planet Jerusalem", "Derech Hebron, Jerusalem", 31.762255, 35.225640, schedule_id="1073", schedule_supported=True, seats_supported=True),
    _cinema("yes-planet-rishon-lezion", "yes_planet", "Planet Rishon LeZion", "HaMea VeEsrim 4, Rishon LeZion", 31.979790, 34.747590, schedule_id="1072", schedule_supported=True, seats_supported=True),

    _cinema("hot-cinema-kfar-saba", "hot_cinema", "Hot Cinema Kfar Saba", "Kfar Saba Green", 32.165405, 34.930022, schedule_id=16, seat_site_id=1197, schedule_supported=True, seats_supported=True),
    _cinema("hot-cinema-petah-tikva", "hot_cinema", "Hot Cinema Petah Tikva", "HaKanyon HaGadol, Petah Tikva", 32.093232, 34.865493, schedule_id=14, seat_site_id=1194, schedule_supported=True, seats_supported=True),
    _cinema("hot-cinema-modiin", "hot_cinema", "Hot Cinema Modiin", "Azrieli Mall Modiin", 31.889012, 34.963161, schedule_id=1, seat_site_id=1183, schedule_supported=True, seats_supported=True),
    _cinema("hot-cinema-rehovot", "hot_cinema", "Hot Cinema Rehovot", "Rehovot Mall", 31.893305, 34.806848, schedule_id=17, seat_site_id=1191, schedule_supported=True, seats_supported=True),
    _cinema("hot-cinema-grand-haifa", "hot_cinema", "Hot Cinema Grand Haifa", "Grand Canyon, Haifa", 32.789711, 35.007822, schedule_id=9, seat_site_id=1195, schedule_supported=True, seats_supported=True),
    _cinema("hot-cinema-kiryat-bialik", "hot_cinema", "Hot Cinema Krion", "Krion Mall, Derech Akko 192, Kiryat Bialik", 32.842737, 35.089856, schedule_id=2, seat_site_id=1184, schedule_supported=True, seats_supported=True),
    _cinema("hot-cinema-karmiel", "hot_cinema", "Hot Cinema Karmiel", "Hutzot Karmiel Mall", 32.928234, 35.324996, schedule_id=15, seat_site_id=1192, schedule_supported=True, seats_supported=True),
    _cinema("hot-cinema-nahariya", "hot_cinema", "Hot Cinema Nahariya", "Nahariya Mall, HaIrit 2, Nahariya", 32.990652, 35.095389, schedule_id=6, seat_site_id=1181, schedule_supported=True, seats_supported=True),
    _cinema("hot-cinema-ashkelon", "hot_cinema", "Hot Cinema Ashkelon", "Ashkelon", 31.681682, 34.558340, schedule_id=8, seat_site_id=1193, schedule_supported=True, seats_supported=True),
    _cinema("hot-cinema-ashdod", "hot_cinema", "Hot Cinema Ashdod", "Sea Mall, Ashdod", 31.792870, 34.639148, schedule_id=5, seat_site_id=1182, schedule_supported=True, seats_supported=True),
    _cinema("hot-cinema-netanya-pop-up", "hot_cinema", "Hot Cinema Netanya Pop-up", "Netanya", 32.321458, 34.853196, schedule_id=3, seat_site_id=1198, schedule_supported=True, seats_supported=True),
    _cinema("hot-cinema-dream-stage-holon", "hot_cinema", "Dream Stage Holon", "Holon", 32.015833, 34.779167, schedule_id=22, seat_site_id=1196, schedule_supported=True, seats_supported=True),

    _cinema("movieland-afula", "movieland", "Movieland Afula", "Blue Valley Mall, Yosef Barzilai 5, Afula", 32.620378, 35.313719, schedule_id=1294, seat_site_id=1294, schedule_supported=True, seats_supported=True),
    _cinema("movieland-bat-yam", "movieland", "Movieland Bat Yam", "BIG Fashion, Yosftal 92, Bat Yam", 32.023600, 34.747000, schedule_id=1296, seat_site_id=1296, schedule_supported=True, seats_supported=True),
    _cinema("movieland-tel-aviv-hatzuk", "movieland", "Movieland Hatzuk Tel Aviv", "Yunitsman 21, Tel Aviv", 32.130900, 34.791000, schedule_id=1293, seat_site_id=1293, schedule_supported=True, seats_supported=True),
    _cinema("movieland-netanya", "movieland", "Movieland Netanya", "Giborei Israel 17, Netanya", 32.275000, 34.855000, schedule_id=1292, seat_site_id=1292, schedule_supported=True, seats_supported=True),
    _cinema("movieland-karmiel", "movieland", "Movieland Karmiel", "HaHaroshet 15, Karmiel", 32.921841, 35.308057, schedule_id=1290, seat_site_id=1290, schedule_supported=True, seats_supported=True),
    _cinema("movieland-haifa", "movieland", "Movieland Haifa", "Azrieli Mall, Moshe Pliman 4, Haifa", 32.785800, 34.966000, schedule_id=1291, seat_site_id=1291, schedule_supported=True, seats_supported=True),

    _cinema("lev-even-yehuda", "lev", "Lev Even Yehuda", "Even Yehuda", 32.269000, 34.887000, schedule_id="לב אבן יהודה", schedule_supported=True),
    _cinema("lev-daniel", "lev", "Lev Daniel", "Lev Daniel", 32.085300, 34.781800, schedule_id="לב דניאל", schedule_supported=True),
    _cinema("lev-smadar", "lev", "Lev Smadar", "Jerusalem", 31.769000, 35.221000, schedule_id="לב סמדר", schedule_supported=True),
    _cinema("lev-omer", "lev", "Lev Omer", "Omer", 31.264000, 34.699000, schedule_id="לב עומר", schedule_supported=True),
    _cinema("lev-ramat-hasharon", "lev", "Lev Ramat HaSharon", "Ramat HaSharon", 32.146000, 34.841000, schedule_id="לב רמת השרון", schedule_supported=True),
    _cinema("lev-raanana", "lev", "Lev Ra'anana", "Ra'anana", 32.184000, 34.871000, schedule_id="לב רעננה", schedule_supported=True),
    _cinema("lev-tel-aviv", "lev", "Lev Tel Aviv", "Dizengoff 50, Tel Aviv", 32.075300, 34.774800, schedule_id="לב תל אביב", schedule_supported=True, seats_supported=True),
)

CINEMAS: tuple[Cinema, ...] = tuple(config.cinema for config in CINEMA_CATALOG)
CINEMA_CONFIG_BY_ID = {config.cinema.id: config for config in CINEMA_CATALOG}
