import os
import re
import sys

for dossier, sous_dossier, fichiers in os.walk('/var/www/vhosts/####/httpdocs/wp/wp-content/plugins/caldera-forms/ui/support'):
    print(dossier)
    print(sous_dossier)
    print(fichiers)


file = open("/var/www/vhosts/####/httpdocs/index.php", "r")

for line in file:
     if re.search(sys.argv[1], line):
         print(line)