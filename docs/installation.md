# Installation

Arbetet delas mellan två datorer:

| Dator | Används till |
|---|---|
| **Debian-servern** (utan skrivbord) | Hämta och bearbeta data med skripten i repot. Eventuellt köra Maps4FS i Docker. |
| **Windows-datorn** | FS25, GIANTS Editor 10, GIMP och QGIS. Allt som har grafiskt gränssnitt. |

Resultatet från servern (höjdkarta, masker och fält) hämtas över till
Windows med git eller `scp`.

## Debian-servern

### 1. Paket och repo

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
git clone https://github.com/dsjodin/FS_sweden_map.git
cd FS_sweden_map
git checkout claude/fervent-allen-oc978z   # tills arbetet är ihopslaget med main
```

### 2. Python-miljö

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`rasterio` levereras med GDAL inbyggt, så inga GDAL-paket från apt behövs.
Python 3.11 (Debian 12) och senare fungerar.

### 3. Hämta data

```bash
source .venv/bin/activate
python scripts/fetch_osm.py
python scripts/fetch_fields.py

# Höjdmodellen kräver Geotorget-kontot. Läs in lösenordet utan att det
# hamnar i skalhistoriken:
export LM_USER=ditt-användarnamn
read -rs LM_PASSWORD && export LM_PASSWORD
python scripts/fetch_heightmap.py
```

### 4. Maps4FS (valfritt, testas i fas 3)

Maps4FS genererar en FS25-grundkarta och har ett webbgränssnitt. Det går att
köra i Docker på servern och öppna i webbläsaren på Windows-datorn via
`http://<serverns-ip>:<port>`. Installera Docker enligt docs.docker.com
(Debian) och följ Maps4FS egna instruktioner för det aktuella Docker-kommandot
och portnumret, eftersom de ändras mellan versioner.

## Windows-datorn

1. **Farming Simulator 25**, för att testa kartan.
2. **GIANTS Editor 10**: logga in på gdn.giants-software.com, gå till
   Downloads och välj GIANTS Editor 10.x för FS25.
3. **GIMP** (gimp.org) för höjdkarta, masker och texturer.
4. **QGIS** (qgis.org, LTR-versionen) för att titta på geodata och jämföra
   med ortofoto.
5. **Git for Windows** (git-scm.com) för att hämta repot.
   Alternativet är att ladda ner zip-filen från GitHub.

Python behövs inte på Windows-datorn, eftersom skripten körs på servern.

### Hämta filer från servern

Har du ändrat eller genererat filer som inte checkas in, hämtar du dem med
`scp` från PowerShell. `scp` ingår i Windows 10 och 11:

```powershell
scp -r användare@server:~/FS_sweden_map/data/lm/hojd .\hojd
```

Har du hellre ett grafiskt program fungerar WinSCP lika bra.
