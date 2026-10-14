# Installation

Arbetet delas mellan två datorer:

| Dator | Används till |
|---|---|
| **Debian-servern** (utan skrivbord) | Hämta och bearbeta data med skripten i repot. |
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

# Lantmäteriets steg kräver Geotorget-kontot. Läs in lösenordet utan att det
# hamnar i skalhistoriken:
export LM_USER=ditt-användarnamn
read -rs LM_PASSWORD && export LM_PASSWORD

# Hela kedjan för en karta (se README för en ny karta):
python scripts/pipeline.py --map tysslinge
```

### Flytta data från den gamla mappstrukturen

Före stödet för flera kartor låg Tysslinges data direkt i `data/` och
`build/`. Efter `git pull` flyttar du den en gång:

```bash
mkdir -p data/tysslinge build/tysslinge
[ -d data/raw ] && mv data/raw data/tysslinge/
[ -d data/lm ] && mv data/lm data/tysslinge/
[ -f data/tysslinge/lm/hojd/dtm_8km.tif ] && mv data/tysslinge/lm/hojd/dtm_8km.tif data/tysslinge/lm/hojd/dtm_total.tif
for f in data preview heightmap.json; do [ -e build/$f ] && mv build/$f build/tysslinge/; done
```

### 4. Kartgeneratorer

Maps4FS har lagts ner och ersatts av webbtjänsten MapToPlay (maptoplay.com),
som inte behöver installeras. Inget mer behövs på servern för den.

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
scp -r användare@server:~/FS_sweden_map/data/tysslinge/lm/hojd .\hojd
```

Har du hellre ett grafiskt program fungerar WinSCP lika bra.
