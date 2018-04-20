import json
import random
import re
import string
import requests
import subprocess
import sys
import fileinput
import hashlib
from pprint import pprint

# Config file
import config

# Some constants
DRY_MODE = True
LOGIN_LENGTH = 8
PASS_LENGTH = 12
PIWIK_PLUGIN_DIR = 'wp-piwik'
PIWIK_PLUGIN_CONFIG_FILENAME = 'wp-piwik/classes/WP_Piwik/Settings.php'
WP_PLUGINS_DIR = 'wp-content/plugins/'

# Pass generator
def pw_gen(size = PASS_LENGTH, chars=string.ascii_letters + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))

print("Running in dry mode, nothing will be done")

# First step, lists vhosts on plesk
# https://support.plesk.com/hc/en-us/articles/213368629-How-to-get-a-list-of-Plesk-domains-and-their-IP-addresses
command = "MYSQL_PWD=`sudo cat /etc/psa/.psa.shadow` mysql -u admin -Dpsa -s -r -e\"SELECT dom.name FROM domains dom LEFT JOIN DomainServices d ON (dom.id = d.dom_id AND d.type = 'web')\""
s = subprocess.Popen([command],stdout=subprocess.PIPE,shell=True).stdout
vhostsList = s.read().splitlines()

# Get existing site list
query = config.PIWIK_URL + "?module=API&method=SitesManager.getAllSites&format=json&token_auth=" + config.TOKEN
response = requests.get(query)
jsonString = response.content
siteList = json.loads(jsonString)

print("======================")
print("Following websites are already registered in Matomo : ")
for site in siteList:
    print(site["name"] + " => " + site["main_url"])
print("======================")

# For file use
# with open(vhostsList, 'rU') as f:

# Iterate each vhost
for line in vhostsList:

  if line[0:3] == "www." in line:
      fqdn = line[4:len(line)]
  else:
      fqdn = line

      print("\n[ "+fqdn+" ]")

      # Get the part before the dot
      left_text = fqdn.partition(".")[0]
      strLength = len(left_text)

      # Limit to 8 chars
      if strLength > LOGIN_LENGTH:
          login = left_text[0:LOGIN_LENGTH]
      else:
          login = left_text

      # -SitesManager.addSite(siteName, urls='', ecommerce='', siteSearch='', searchKeywordParameters='',
      #                      searchCategoryParameters='', excludedIps='', excludedQueryParameters='', timezone='',
      #                      currency='', group='', startDate='', excludedUserAgents='', keepURLFragments='', type='',
      #                      settingValues='', excludeUnknownUrls='')

      # Site part
      siteData = {
          "siteName": "www."+fqdn,
          "urls": "www."+fqdn,
          "ecommerce": "false",
          "siteSearch": "",
          "searchKeywordParameters": "",
          "searchCategoryParameters": "",
          "excludedIps": "",
          "excludedQueryParameters": "",
          "timezone": "",
          "currency": "",
          "group": "",
          "startDate": "",
          "excludedUserAgents": "",
          "keepURLFragments": "",
          "type": "",
          "settingValues": "",
          "excludeUnknownUrls": ""
      }

      sys.stdout.write("Adding site to Matomo : ")
      if not DRY_MODE:
          if not siteData["siteName"] in siteList:
              response = requests.post(config.PIWIK_URL, json=siteData)
              if response.status_code == 200:
                  print("OK")
              else:
                  print("Something wrong happened =/, sorry")

          else:
              print(siteData["siteName"] + " already exists in Matomo")

          # Fetch site ID
          getSiteID = {
              "module": "API",
              "method": "SitesManager.getSitesIdFromSiteUrl",
              "url": siteData['urls'],
              "format": "json",
              "token_auth": config.TOKEN,
          }
          response = requests.get(config.PIWIK_URL, json=getSiteID)
          if response.status_code == 200:
              print("OK")
              jsonString = response.content
              siteID = json.loads(jsonString)
          else:
              print("Unable to get site ID from URL [ " + siteData['urls'] + " ] Status code : " + response.status_code)
      else:
          print("Dry run =)")

      # User part
      password = pw_gen(PASS_LENGTH)
      data = {
          "module": "API",
          "method": "UsersManager.addUser",
          "format": "json",
          "token_auth": config.TOKEN,
          "userLogin": login,
          "password": password,
          "email": "info@"+fqdn
      }

      print("Generating user credentials...")
      print("Login : " + data["userLogin"])
      print("Pass : " + data["password"])
      sys.stdout.write("User creation : ")
      if not DRY_MODE:
          response = requests.post(PIWIK_URL, json=data)
          if response.status_code == 200:
              print("OK")

              # Allow this user to manager his own site
              #- UsersManager.setUserAccess(userLogin, access, idSites)
              userAccess = {
                  "userLogin": data["userLogin"],
                  "access": "UsersManager.UserAccess.admin",
                  "idSites": siteID
              }

              sys.stdout.write("Set user access : ")
              if not DRY_MODE:
                  response = requests.post(config.PIWIK_URL, json=userAccess)
                  if response.status_code == 200:
                      print("OK")
              else:
                  print("Dry run =)")
          else:
              print("Dry run =)")
      else:
          print("Dry run =)")


      # Prepare user pass MD5
      md5Pass = hashlib.md5(password.encode('utf-8')).hexdigest()

      # Retrieve user's API Token
      userToken = {
          "module": "API",
          "method": "UsersManager.getTokenAuth",
          "userLogin": login,
          "md5Password": md5Pass,
          "format": "json",
          "token_auth": config.TOKEN,
      }

      sys.stdout.write("Fetch user's token : ")

      query = config.PIWIK_URL + "?module=API&method=UsersManager.getTokenAuth&userLogin="+login+"&md5Password="+md5Pass+"&format=json&token_auth="+config.TOKEN
      response = requests.get(query)
      if response.status_code == 200:
          jsonString = response.content
          unserData = json.loads(jsonString)
          userToken = unserData["value"]
          print(userToken)
      else:
          print("Unable to fetch token for user " + login + " Status code : " + response.status_code)

      # Plugin deploiement part
      # Prepare custom config for current vhost

      # MD5 sum regex
      tokenRegex = re.compile(r"piwik_token.*([a-fA-F\d]{32})", re.IGNORECASE)
      replacements = {"'piwik_token' => '',": "'piwik_token' => '"+userToken+"',"}
      lines = []

      OUTPUT_FILE = PIWIK_PLUGIN_CONFIG_FILENAME + "_tmp"
      with open(PIWIK_PLUGIN_CONFIG_FILENAME) as infile, open(OUTPUT_FILE, 'w') as outfile:
          for line in infile:
              tmpLine = tokenRegex.sub(userToken, line)
              outfile.write(tmpLine)

      # Check config file was successfully adapted
      cmd = "grep "+userToken+" "+OUTPUT_FILE+" >/dev/null ; echo $?;"
      print(cmd)
      s = subprocess.Popen([cmd], stdout=subprocess.PIPE, shell=True).stdout
      output = s.read()


      # Open index.php file in vhost web root directory
      # _> find out wordpress install path
      findCmd = 'grep -h --color /var/www/vhosts/'+fqdn+'/web/index.php -e "/wp-blog-header.php" 2>/dev/null'

      # 2. Follow the link
      # Typical output
      # require( dirname( __FILE__ ) . '/2017/wp-blog-header.php' );
      # require( dirname( __FILE__ ) . '/__new/wp-blog-header.php' );
      # require( dirname( __FILE__ ) . '/ru/wp-blog-header.php' );
      # require( dirname( __FILE__ ) . '/site/wp-blog-header.php' );
      # require( dirname( __FILE__ ) . '/wp-blog-header.php' );

      s = subprocess.Popen([findCmd], stdout=subprocess.PIPE, shell=True).stdout
      entryPointLines = s.read().splitlines()

      # \s?(require\b|require_once\b)\(\s?.*'(.*)wp-blog-header.php'\s?\);
      pattern = "\s?(require\b|require_once\b)\(\s?.*'(.*)wp-blog-header.php'\s?\);"
      for line in entryPointLines:
          matchObj = re.match(pattern, line, flags=0)
          if matchObj:
              print(matchObj.group(2))


      # Move file to destination
      #cmd = "sudo cp " + OUTPUT_FILE + " " + "/var/www/vhosts/" + fqdn + "/httpdocs/" + WP_PLUGINS_DIR + PIWIK_PLUGIN_CONFIG_FILENAME
      #print(cmd)
      #s = subprocess.Popen([cmd], stdout=subprocess.PIPE, shell=True).stdout
      #output = s.read()

      print(output)
      exit(0)

      print("\n")