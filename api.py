import os
from stat import *
import json
import random
import re
import string
import requests
import subprocess
import sys
import hashlib
import csv
from time import sleep
from pwd import getpwuid
from grp import getgrgid

# Config file
import config

# Pass generator
def pw_gen(size=config.PASS_LENGTH, chars=string.ascii_letters + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


# Function definition is here
def runCommand(cmd, bool):
    # Run command
    s = subprocess.Popen([cmd], stdout=subprocess.PIPE, shell=True).stdout

    # 1 or 0 is expected through ; echo $?
    if bool is True:
        output = int(s.read())

        # Error occured
        if output is not 0:
            print("Oups =|")
            return False
        else:
            print("OK")
            return True
    else:
        output = s.read()
        return output


if config.DRY_MODE:
    print("Running in dry mode, nothing will be done")

# First step, lists vhosts on plesk
# https://support.plesk.com/hc/en-us/articles/213368629-How-to-get-a-list-of-Plesk-domains-and-their-IP-addresses
command = "MYSQL_PWD=`sudo cat /etc/psa/.psa.shadow` mysql -u admin -Dpsa -s -r -e\"SELECT dom.name FROM domains dom LEFT JOIN DomainServices d ON (dom.id = d.dom_id AND d.type = 'web')\""
s = subprocess.Popen([command], stdout=subprocess.PIPE, shell=True).stdout
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
    # ss = site["main_url"].encode('utf8')
    # siteNameList.append(ss)
print("======================")

# Debug
# vhostsList = []
# vhostsList.append("lacotel.ch")

# Iterate each vhost
for line in vhostsList:

    if line[0:3] == "www." in line:
        url = line
        fqdn = line[4:len(line)]
    else:
        fqdn = line
        url = 'www.' + line
        print("\n[ " + fqdn + " ]")

        # Get the part before the dot
        left_text = fqdn.partition(".")[0]
        strLength = len(left_text)

        # Limit to 8 chars
        if strLength > config.LOGIN_LENGTH:
            login = left_text[0:config.LOGIN_LENGTH]
        else:
            login = left_text

        # -SitesManager.addSite(siteName, urls='', ecommerce='', siteSearch='', searchKeywordParameters='',
        #                      searchCategoryParameters='', excludedIps='', excludedQueryParameters='', timezone='',
        #                      currency='', group='', startDate='', excludedUserAgents='', keepURLFragments='', type='',
        #                      settingValues='', excludeUnknownUrls='')

        # Adding website returns its ID
        query = config.PIWIK_URL + "?module=API&method=SitesManager.addSite&siteName=" + url + "&urls=" + url + "&format=json&token_auth=" + config.TOKEN
        sys.stdout.write("Adding site to Matomo : ")
        if not config.DRY_MODE:

            found = False
            for site in siteList:
                regex = r".*\b(?=\w)" + re.escape(fqdn) + r"\b(?!\w).*"
                if re.search(regex, site['name'], re.IGNORECASE) or re.search(regex, site['main_url'], re.IGNORECASE):
                    found = True
                    print(url + " already exists in Matomo")

            if found == True:
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
                print("Unable to get site ID from URL [ " + url + " ] Status code : " + response.status_code)
                exit(1)

        else:
            print("Dry run =)")

        sleep(1)

        # User part
        password = pw_gen(config.PASS_LENGTH)

        data = []
        data.append(url)
        data.append(login)
        data.append(password)

        # Save credentials
        with open(config.CREDENTIALS_FILE, 'a') as resultFile:
            wr = csv.writer(resultFile, dialect='excel')
            wr.writerow(data)

        print("Generating user credentials...")
        print("Login : " + login)
        print("Pass : " + password)
        sys.stdout.write("User creation : ")
        if not config.DRY_MODE:
            query = config.PIWIK_URL + "?module=API&method=UsersManager.addUser&userLogin=" + login + "&password=" + password + "&format=json&email=info@" + fqdn + "&token_auth=" + config.TOKEN
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
                # - UsersManager.setUserAccess(userLogin, access, idSites)
                query = config.PIWIK_URL + "?module=API&method=UsersManager.setUserAccess&userLogin=" + login + "&access=admin&idSites=" + siteID + "&format=json&token_auth=" + config.TOKEN
                sys.stdout.write("Set user access : ")
                if not config.DRY_MODE:
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
        query = config.PIWIK_URL + "?module=API&method=UsersManager.getTokenAuth&userLogin=" + login + "&md5Password=" + md5Pass + "&format=json&token_auth=" + config.TOKEN
        if not config.DRY_MODE:
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

        with open(config.PIWIK_PLUGIN_CONFIG_FILENAME) as infile, open(OUTPUT_FILE, 'w') as outfile:
            for line in infile:
                # Setup connections & auth stuff
                line = re.sub(r"'piwik_token'\s?=>\s?'',", "'piwik_token' => '" + userToken + "',", line)
                line = re.sub(r"'piwik_url'\s?=>\s?'',", "'piwik_url' => '" + os.path.dirname(config.PIWIK_URL) + "/',",
                              line)
                line = re.sub(r"'piwik_user'\s?=>\s?'',", "'piwik_user' => '" + login + "',", line)

                # 'default_date' => 'yesterday',
                line = re.sub(r"'default_date'\s?=>\s?'',", "'default_date' => 'current_month',", line)

                # last30
                line = re.sub(r"'dashboard_widget'\s?=>\s?'',", "'dashboard_widget' => 'true',", line)

                # Show admin toolbar for quick access
                line = re.sub(r"'toolbar'\s?=>\s?.*,", "'toolbar' => true,", line)

                line = re.sub(r"'plugin_display_name'\s?=>\s?.*,", "'plugin_display_name' => '"+config.DISPLAY_NAME+"',", line)
                line = re.sub(r"'piwik_shortcut'\s?=>\s?.*,", "'piwik_shortcut' => true,", line)

                # Enable tracking
                line = re.sub(r"'track_mode'\s?=>\s?.*,", "'track_mode' => 'default',", line)

                # Tracking code load in the footer
                line = re.sub(r"'track_codeposition'\s?=>\s?.*,", "'track_codeposition' => 'footer',", line)

                # Track only visible items
                line = re.sub(r"'track_content'\s?=>\s?.*,", "'track_content' => 'visible',", line)

                # Track internal search
                line = re.sub(r"'track_search'\s?=>\s?.*,", "'track_search' => true,", line)

                # Track 404 errors
                line = re.sub(r"'track_404'\s?=>\s?.*,", "'track_404' => true,", line)

                # https://developer.matomo.org/guides/tracking-javascript-guide#tracking-one-domain-and-its-subdomains-in-the-same-website
                # Track accross sub-domains
                line = re.sub(r"'track_across'\s?=>\s?.*,", "'track_across' => true,", line)

                # Do not consider accessing sub-domain as outgoing link
                line = re.sub(r"'track_across_alias'\s?=>\s?.*,", "'track_across_alias' => true,", line)

                # When enabled, it will make sure to use the same visitor ID for the same visitor across several domains.
                # This works only when this feature is enabled because the visitor ID is stored in a cookie and cannot be read on the other domain by default.
                # When this feature is enabled, it will append a URL parameter "pk_vid" that contains the visitor ID
                # when a user clicks on a URL that belongs to one of your domains.
                # For this feature to work, you also have to configure which domains should be treated as local in your Piwik website settings.
                # This feature requires Piwik 3.0.2.
                line = re.sub(r"'track_crossdomain_linking'\s?=>\s?.*,", "'track_crossdomain_linking' => false,", line)

                # DNS Prefetch for better performances ( 'dnsprefetch' => true, )
                line = re.sub(r"'dnsprefetch'\s?=>\s?.*,", "'dnsprefetch' => true,", line)

                # ask Rocket Loader to ignore the script ( in case CloudFlare is being used )
                line = re.sub(r"'track_datacfasync'\s?=>\s?.*,", "'track_datacfasync' => true,", line)

                # Disable update notices ( 'update_notice' => 'enabled' )
                line = re.sub(r"'update_notice'\s?=>\s?.*,", "'update_notice' => 'disabled',", line)

                outfile.write(line)

        print("OK")

        # Check config file was successfully adapted
        cmd = "grep " + userToken + " " + OUTPUT_FILE + " >/dev/null ; echo $?;"
        sys.stdout.write("Checking settings file : ")
        if runCommand(cmd, True) is not True:
            exit(1)

        # Open index.php file in vhost web root directory
        # _> find out wordpress install path
        #
        # 2. Follow the link
        # Typical output
        # require( dirname( __FILE__ ) . '/2017/wp-blog-header.php' );
        # ...
        # require( dirname( __FILE__ ) . '/site/wp-blog-header.php' );
        # require( dirname( __FILE__ ) . '/wp-blog-header.php' );
        findCmd = 'grep -h ' + config.VHOSTS_DIR + fqdn + '/' + config.WEB_ROOT_DIR + '/index.php -e "/wp-blog-header.php" 2>/dev/null'
        sys.stdout.write("Find out WP install path [ " + findCmd + " ] : ")
        output = runCommand(findCmd, False)
        entryPointLines = output.splitlines()

        # \s?(require\b|require_once\b)\(\s?.*'(.*)wp-blog-header.php'\s?\);
        # Parse command output
        # pattern = "\s?(require\b|require_once\b)\(\s?.*'(.*)wp-blog-header.php'\s?\);"
        wpFound = False
        for line in entryPointLines:
            matchObj = re.match(r"\s?(require\b|require_once\b)\(\s?.*'(.*)wp-blog-header.php'\s?\);", line, flags=0)
            if matchObj:
                wpInstallPath = matchObj.group(2)
                wpFound = True
                print(matchObj.group(2))

        if not wpFound:
            print("No Wordpress instances out there, skipping this vhost")
            continue

        # Move file to destination
        cmd = "sudo cp -R " + config.PIWIK_PLUGIN_DIR + " " + config.VHOSTS_DIR + fqdn + "/" + config.WEB_ROOT_DIR + wpInstallPath + config.WP_PLUGINS_DIR + " ; echo $?"
        sys.stdout.write("Moving plugin to vhost plugins directory : ")
        if config.DRY_MODE:
            print("Dry run =)")
        else:
            if runCommand(cmd, True) is not True:
                exit(1)

        cmd = "sudo cp " + OUTPUT_FILE + " " + config.VHOSTS_DIR + fqdn + "/" + config.WEB_ROOT_DIR + wpInstallPath + config.WP_PLUGINS_DIR + config.PIWIK_PLUGIN_CONFIG_FILENAME + "; rm config_tmp"
        sys.stdout.write("Updating Matomoto settings file : ")
        if config.DRY_MODE:
            print("Dry run =)")
        else:
            runCommand(cmd, False)

        # Set correct permissions
        # Use index.php entry point's permissions as reference
        filename = config.VHOSTS_DIR + fqdn + '/' + config.WEB_ROOT_DIR + '/index.php'
        indexPermissions = oct(os.stat(filename)[ST_MODE])[-4:]
        indexOwner = getpwuid(os.stat(filename).st_uid).pw_name
        indexGroup = getgrgid(os.stat(filename).st_gid).gr_name

        # set correct owner
        cmd = "sudo chown -R " + indexOwner + ":" + indexGroup + " " + config.PIWIK_PLUGIN_DIR + " " + config.VHOSTS_DIR + fqdn + "/" + config.WEB_ROOT_DIR + wpInstallPath + config.WP_PLUGINS_DIR + " ; echo $?"
        sys.stdout.write("Setting the right owner : ")
        if config.DRY_MODE:
            print("Dry run =)")
        else:
            if runCommand(cmd, True) is not True:
                exit(1)

        # Prepare payload for plugin activation
        cmd = "sudo cp " + config.SCRIPT_PLUGIN_ENABLER + " " + config.VHOSTS_DIR + fqdn + "/" + config.WEB_ROOT_DIR + wpInstallPath + "; echo $?"
        sys.stdout.write("Preparing payload for plugin activation [ " + cmd + " ] : ")
        if config.DRY_MODE:
            print("Dry run =)")
        else:
            if runCommand(cmd, True) is not True:
                exit(1)

        # Enable Matomo plugin
        cmd = "php " + config.VHOSTS_DIR + fqdn + "/" + config.WEB_ROOT_DIR + wpInstallPath + config.SCRIPT_PLUGIN_ENABLER + " " + config.PIWIK_PLUGIN_DIR + "/wp-piwik.php"
        sys.stdout.write("Activating Matomo plugin [ " + cmd + " ] : ")
        if config.DRY_MODE:
            print("Dry run =)")
        else:
            output = runCommand(cmd, False)
            print(output)

        print("\n")