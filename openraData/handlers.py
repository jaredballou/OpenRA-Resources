import shutil
import os
import magic
import zipfile
import string
from subprocess import Popen, PIPE

from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import User
from openraData.models import Maps

class MapHandlers():
    
    def __init__(self, map_full_path_filename="", map_full_path_directory="", minimap_filename=""):
        self.map_is_uploaded = False
        self.minimap_generated = False
        self.maphash = ""
        self.LintPassed = False
        self.map_full_path_directory = map_full_path_directory
        self.map_full_path_filename = map_full_path_filename
        self.minimap_filename = minimap_filename
        self.currentDirectory = os.getcwd() + os.sep    # web root
        self.UID = "1"
        self.LOG = []

        self.MapMod = ""
        self.MapTitle = ""
        self.MapAuthor = ""
        self.MapTileset = ""
        self.MapType = ""
        self.MapSize = ""
        self.MapDesc = ""
        self.MapPlayers = 0

    def ProcessUploading(self, user_id, f, info, rev=1, pre_r=0):
        tempname = '/tmp/oramaptemp.oramap'
        with open(tempname, 'wb+') as destination:
            for chunk in f.chunks():
                destination.write(chunk)

        mime = magic.Magic(mime=True)
        mimetype = mime.from_file(tempname)
        if mimetype != 'application/zip' or os.path.splitext(f.name)[1] != '.oramap':
            self.LOG.append('Failed. Unsupported file type.')
            return False

        name = f.name
        badChars = ": ; < > @ $ # & ( ) % '".split()
        for badchar in badChars:
            name = name.replace(badchar, "_")
        name = name.replace(" ", "_")

        z = zipfile.ZipFile(tempname, mode='a')
        yamlData = ""
        mapFileContent = []
        for filename in z.namelist():
            mapFileContent.append(filename)
            if filename == "map.yaml":
                mapbytes = z.read(filename)
                yamlData = mapbytes.decode("utf-8")
        if "map.yaml" not in mapFileContent or "map.bin" not in mapFileContent:
            self.LOG.append('Failed. Invalid map format.')
            return False

        #Load basic map info
        for line in string.split(yamlData, '\n'):
            if line[0:5] == "Title":
                self.MapTitle = line[6:].strip().replace("'", "''")
            if line[0:11] == "RequiresMod":
                self.MapMod = line[12:].strip().lower()
            if line[0:6] == "Author":
                self.MapAuthor = line[7:].strip().replace("'", "''")
            if line[0:7] == "Tileset":
                self.MapTileset = line[8:].strip().lower()
            if line[0:4] == "Type":
                self.MapType = line[5:].strip()
            if line[0:11] == "Description":
                self.MapDesc = line[12:].strip().replace("'", "''")
            if line[0:7] == "MapSize":
                self.MapSize = line[8:].strip()
            if line.strip()[0:8] == "Playable":
                state = line.split(':')[1]
                if state.strip().lower() in ['true', 'on', 'yes', 'y']:
                    self.MapPlayers += 1
            if line.strip()[0:13] == "UseAsShellmap":
                state = line.split(':')[1]
                if state.strip().lower() in ['true', 'on', 'yes', 'y']:
                    self.LOG.append('Failed. Reason: %s' % line)
                    return False

        try:
            self.UID = str(int(Maps.objects.latest('id').id) + 1)
        except: # table is empty, using default value
            pass
        self.map_full_path_directory = self.currentDirectory + __name__.split('.')[0] + '/data/maps/' + self.UID.rjust(7, '0') + '/'
        if not os.path.exists(self.map_full_path_directory):
            os.makedirs(self.map_full_path_directory + 'content')
        self.map_full_path_filename = self.map_full_path_directory + name
        self.minimap_filename = os.path.splitext(name)[0] + ".png"

        shutil.move(tempname, self.map_full_path_filename)

        self.map_is_uploaded = True
        self.flushLog( ['Map was successfully uploaded as "%s"' % name] )
        self.flushLog( [info] )
        
        self.GetHash()
        self.UnzipMap()
        self.LintCheck()

        u = User.objects.get(pk=user_id)
        transac = Maps(
            user = u,
            title = self.MapTitle,
            description = self.MapDesc,
            info = info,
            author = self.MapAuthor,
            map_type = self.MapType,
            players = self.MapPlayers,
            game_mod = self.MapMod,
            map_hash = self.maphash,
            width = self.MapSize.split(',')[0],
            height = self.MapSize.split(',')[1],
            tileset = self.MapTileset,
            revision = rev,
            pre_rev = pre_r,
            next_rev = 0,
            downloading = True,
            requires_upgrade = not self.LintPassed,
            advanced_map = False,
            posted = timezone.now(),
            viewed = 0,
            )
        transac.save()
        self.UID = transac.id

        self.GenerateMinimap()

    def UnzipMap(self):
        pass

    def GetHash(self):
        os.chdir(settings.OPENRA_PATH)

        command = 'mono OpenRA.Utility.exe --map-hash ' + self.map_full_path_filename
        proc = Popen(command.split(), stdout=PIPE).communicate()
        self.maphash = proc[0].strip()
        self.flushLog(proc)

        os.chdir(self.currentDirectory)

    def LintCheck(self):
        self.LintPassed = True

    def GenerateMinimap(self):
        os.chdir(settings.OPENRA_PATH)

        command = 'mono OpenRA.Utility.exe --map-preview ' + self.map_full_path_filename
        proc = Popen(command.split(), stdout=PIPE).communicate()
        self.flushLog(proc)

        shutil.move(settings.OPENRA_PATH + self.minimap_filename,
                self.map_full_path_directory + 'content/' + self.minimap_filename)        
        if proc[1] == None: # no output in stderr
            self.minimap_generated = True

        os.chdir(self.currentDirectory)

    def flushLog(self, output=[]):
        logfile = open(self.map_full_path_directory + "log", "a")
        for line in output:
            if line != None:
                logfile.write(line.strip() + "\n")
                self.LOG.append(line.strip())
        logfile.close()
        return True