import json
import random
import re
import string
import requests
import subprocess
import sys
import hashlib
from time import sleep

# Config file
import config

# Some constants
DRY_MODE = False
LOGIN_LENGTH = 8
PASS_LENGTH = 12
PIWIK_PLUGIN_DIR = 'wp-piwik'
PIWIK_PLUGIN_CONFIG_FILENAME = 'wp-piwik/classes/WP_Piwik/Settings.php'
WP_PLUGINS_DIR = 'wp-content/plugins/'
WEB_ROOT_DIR = 'httpdocs'

# Pass generator
def pw_gen(size = PASS_LENGTH, chars=string.ascii_letters + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))

if DRY_MODE:
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

#if siteList['result'] == 'error':
#    print(siteList['message'])
#    exit(1)

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
      url = 'www.'+fqdn

      # Adding website returns its ID
      query = config.PIWIK_URL + "?module=API&method=SitesManager.addSite&siteName="+url+"&urls="+url+"&format=json&token_auth=" + config.TOKEN
      sys.stdout.write("Adding site to Matomo : ")
      if not DRY_MODE:
          if url in siteList:
              print(url + " already exists in Matomo")
              break

          # Register new website
          response = requests.post(query)

          # Check response status
          if response.status_code == 200:

              # Make sure we have a non empty response
              if response.text:
                  jsonStr = json.loads(response.text)
                  siteID = jsonStr["value"]

                  # Check if we have a numeric ID
                  try:
                      i = float(siteID)
                  except (ValueError, TypeError):
                      print('Expected a numeric value for siteID')
                      exit(1)

                  # back to string
                  siteID = str(siteID)
                  print("OK [ " + siteID + " ]")
              else:
                  print("Empty response from API")
                  exit(1)

          else:
              print("Unable to get site ID from URL [ " + siteData[
                  'urls'] + " ] Status code : " + response.status_code)
              exit(1)

      else:
          print("Dry run =)")

      # User part
      password = pw_gen(PASS_LENGTH)
      print("Generating user credentials...")
      print("Login : " + login)
      print("Pass : " + password)
      sys.stdout.write("User creation : ")
      if not DRY_MODE:
          query = config.PIWIK_URL + "?module=API&method=UsersManager.addUser&userLogin=" + login + "&password=" + password + "&format=json&email=info@"+fqdn+"&token_auth=" + config.TOKEN
          response = requests.post(query)
          if response.status_code == 200 and response.text:

              jsonStr = json.loads(response.text)
              if isinstance(jsonStr, dict):
                  # Eventuals errors message from API
                  if jsonStr["result"] is not None:
                      if jsonStr["result"] == 'success':
                          print("OK")
                      else:
                          print(jsonStr["result"] + " => " + jsonStr["message"])
                          exit(1)

              # Allow this user to manager his own site
              #- UsersManager.setUserAccess(userLogin, access, idSites)
              query = config.PIWIK_URL + "?module=API&method=UsersManager.setUserAccess&userLogin=" + login + "&access=admin&idSites="+siteID+"&format=json&token_auth=" + config.TOKEN
              sys.stdout.write("Set user access : ")
              if not DRY_MODE:
                  response = requests.post(query)
                  if response.status_code == 200 and response.text:
                      print("OK")
                  else:
                      print("Oups =\ ")
                      exit(1)
              else:
                  print("Dry run =)")
          else:
              print("Oups =\ [ " + response.status_code + " ] " + response.headers)
              exit(1)
      else:
          print("Dry run =)")

      # Prepare user pass MD5
      md5Pass = hashlib.md5(password.encode('utf-8')).hexdigest()

      # Retrieve user's API Token
      sys.stdout.write("Fetch user's token : ")
      query = config.PIWIK_URL + "?module=API&method=UsersManager.getTokenAuth&userLogin="+login+"&md5Password="+md5Pass+"&format=json&token_auth="+config.TOKEN
      if not DRY_MODE:
          response = requests.get(query)
          if response.status_code == 200:
              jsonString = response.content
              unserData = json.loads(jsonString)
              userToken = unserData["value"]
              print(userToken)
          else:
              print("Unable to fetch token for user " + login + " Status code : " + response.status_code)
      else:
          userToken = "FalseTokenForInstance"
          print("Dry mode =)")

      # Plugin deploiement part
      # Prepare custom config for current vhost

      OUTPUT_FILE = "config_tmp"
      sys.stdout.write("Prepare settings file : ")

      with open(PIWIK_PLUGIN_CONFIG_FILENAME) as infile, open(OUTPUT_FILE, 'w') as outfile:
          for line in infile:
              line = re.sub(r"'piwik_token'\s?=>\s?'',", "'piwik_token' => '"+userToken+"',", line)
              line = re.sub(r"'piwik_url'\s?=>\s?'',", "'piwik_url' => '"+config.PIWIK_URL+"',", line)
              line = re.sub(r"'piwik_user'\s?=>\s?'',", "'piwik_user' => '"+login+"',", line)
              line = re.sub(r"'toolbar'\s?=>\s?.*,", "'toolbar' => true,", line)
              outfile.write(line)
      if not DRY_MODE:
          print("Done")
      else:
          print("Dry mode =)")

      # Check config file was successfully adapted
      cmd = "grep "+userToken+" "+OUTPUT_FILE+" >/dev/null ; echo $?;"
      sys.stdout.write("Checking settings file [ " + cmd + " ] : ")
      s = subprocess.Popen([cmd], stdout=subprocess.PIPE, shell=True).stdout
      output = s.read()
      if output is None:
          print("Oups =/")
          exit(1)
      else:
          print("Good")

      # Open index.php file in vhost web root directory
      # _> find out wordpress install path
      findCmd = 'grep -h /var/www/vhosts/' + fqdn + '/' + WEB_ROOT_DIR + '/index.php -e "/wp-blog-header.php" 2>/dev/null'
      sys.stdout.write("Find out WP install path [ " + findCmd + " ] : ")

      # 2. Follow the link
      # Typical output
      # require( dirname( __FILE__ ) . '/2017/wp-blog-header.php' );
      # ...
      # require( dirname( __FILE__ ) . '/site/wp-blog-header.php' );
      # require( dirname( __FILE__ ) . '/wp-blog-header.php' );

      s = subprocess.Popen([findCmd], stdout=subprocess.PIPE, shell=True).stdout
      entryPointLines = s.read().splitlines()

      # \s?(require\b|require_once\b)\(\s?.*'(.*)wp-blog-header.php'\s?\);
      # Parse command output
      # pattern = "\s?(require\b|require_once\b)\(\s?.*'(.*)wp-blog-header.php'\s?\);"
      for line in entryPointLines:
          matchObj = re.match(r"\s?(require\b|require_once\b)\(\s?.*'(.*)wp-blog-header.php'\s?\);", line, flags=0)
          if matchObj:
              wpInstallPath = matchObj.group(2)
              print(matchObj.group(2))

      # TODO : set correct permissions

      # Move file to destination
      cmd = "sudo cp -R " + PIWIK_PLUGIN_DIR + " " + "/var/www/vhosts/" + fqdn + "/httpdocs" + wpInstallPath + WP_PLUGINS_DIR + " ; echo $?"
      sys.stdout.write("Moving plugin to vhost plugins directory [ " + cmd + " ] : ")
      if not DRY_MODE:
          s = subprocess.Popen([cmd], stdout=subprocess.PIPE, shell=True).stdout
          output = s.read()
          if output is None:
              print("Something went wrong.. ")
              exit(1)
          else:
              print("Successfully moved to WP instance")
      else:
          print("Dry run =)")

      cmd = "sudo cp " + OUTPUT_FILE + " " + "/var/www/vhosts/" + fqdn + "/httpdocs" + wpInstallPath + WP_PLUGINS_DIR + PIWIK_PLUGIN_CONFIG_FILENAME + "; rm config_tmp"
      sys.stdout.write("Updating Matomoto settings file [ " + cmd + " ] : ")
      if not DRY_MODE:
          s = subprocess.Popen([cmd], stdout=subprocess.PIPE, shell=True).stdout
          output = s.read()
          print("Done")
      else:
          print("Dry run =)")

      exit(0)
      print("\n")