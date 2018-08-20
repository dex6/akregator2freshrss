# akregator2freshrss

This repo contains some usable (I hope) scripts which will help you migrate your RSS feed list and complete articles archive from [Akregator](https://userbase.kde.org/Akregator) to [FreshRSS](https://freshrss.org/).

Akregator is a desktop application, originating from [KDE](https://www.kde.org/) project. This is a great RSS reader, I used it for over 10 years, however I've finally come to a conclusion that ability to read RSS news on only one PC is quite limiting in the era of tablets and mobile phones... Therefore I've searched for another solution, and a web-based self-hostable reader called FreshRSS is the answer I've found. It's web based, so all you need is a web browser; has scalable modern UI, so it looks great on 5" screen without a dedicated app; and it's self-hostable so you own your data an nobody will [close the service](https://www.google.com/reader/about/) but you. FreshRSS isn't perfect either, it lacks some Akregator features I like (nested categories and three-pane reading view, for example), but I'm ready to trade them for greater mobility FreshRSS offers.


### Status

I've developed and tested these scripts using:

- Akregator v5.8.3 from KDE Applications 18.04.3
- FreshRSS v1.11.1
- archive of 100 feeds with 27k articles

These were most recent versions during creation of these scripts (Jul-Aug, 2018). Since these scripts are "use once and forget" type, I no longer actively use/test them, but I hope they should work with more recent versions. Also because of that once-in-a-lifetime nature, the migration process is quite crude and not very user friendly, but since FreshRSS is self-hostable and requires some technical skills to install, and you seem to know what github is, I'm assuming you know what you are doing after all.


### Prerequisites

- FreshRSS installed using MySQL database (sorry, Postgres/SQLite are not supported; PR would be welcomed)
- SSH access to your FreshRSS host to run PHP scripts ([FreshRSS CLI](https://github.com/FreshRSS/FreshRSS/blob/master/cli/README.md))
- Python 2 on you desktop host (where Akregator archive is) with following extra packages:
  - [MySQLdb](http://mysql-python.sourceforge.net/MySQLdb.html)
  - [lxml](https://github.com/lxml/lxml)
  - [metakit](https://github.com/jnorthrup/metakit)
- Ability to connect remotely from your desktop machine to MySQL running on your web server via TCP (ssh tunnel is enough if MySQL listens on 127.0.0.1)

First two python deps (MySQLdb and lxml) are pretty standard and your distro probably ships them using native package manager. Metakit is a backend DB which Akregator uses to store its archive, and it may be harder to obtain. It supports only Python 2, so these scripts cannot be run using Python 3. If metakit package is not present in your distro repository, you may install it manually using following command sequence:

```bash
git clone https://github.com/jnorthrup/metakit.git
cd metakit/builds
../unix/configure
make -j4
cd ../python
python2 setup.py build -b ../builds
python2 setup.py install --user
```

SSH tunnel to your MySQL can be established using:

```bash
ssh -L 3306:127.0.0.1:3306 <your-freshrss-host>
```


### Migration Instructions

#### Preparation

1. If you have installed a cron job to actualize FreshRSS, disable it temporarily so it does not fire in the middle of migration possibly breaking something.

2. If you wish to test migration scripts, create a separate test user in FreshRSS and use it instead of your primary account. In case something goes wrong, it's easy to delete and create user account again.

3. If you have already imported some feeds from Akregator, or added them manually to the FreshRSS, remove them. It's safe to leave feeds which are not present in Akregator, though.

4. Clone this repository and set proper settings in _a2f_config.py_ file, esp. FreshRSS login name and DB credentials.


#### Config Migration (manual part)

5. Log in to FreshRSS using web browser, open Settings / Archiving panel. Set the same values you use in Akregator for:

   - "Minimum number of articles to keep by feed" (FreshRSS) = "Archive / Limit feed archive size to" (Akregator)
   - "Do not automatically refresh more often than" = "General / Fetch feeds every"

6. Look around, set other options as you like. I'm particularly using in the "Reading" panel:
   - "Number of articles per page": 50
   - "Articles to display": Show all articles
   - unchecked: "Hide categories & feeds with no unread articles"
   - unchecked: "Mark article as read... while scrolling"

   This gives more Akregator-like experience, but these are optional - you may set them as you like.

7. Log out from your FreshRSS.


#### Real Migration

8. Open Akregator, hit "Fetch all feeds", wait until fetching finishes. Read articles for the last time in Akregator, if you like.

9. Quit Akregator. Don't just close it to systray; exit it completely via File->Quit. It's important that Akregator is NOT running during the migration process.

10. On your desktop, enter the cloned akregator2freshrss repo directory and run (as ordinary user; not as root):

```bash
python2 akregator2zip.py
```

   This script produces a zip file, which contains feed list (OPML) and all articles exported in format FreshRSS accepts them.

11. Upload resulting zip file to your web server and execute following command _(substitute www-data=user of your apache/nginx process; FreshRSS_user=user login to your FreshRSS instance; ensure path to CLI script and zipfile are correct; you may need to switch to sudo, read more [here](https://github.com/FreshRSS/FreshRSS/blob/master/cli/README.md))_:

```bash
cd /path/where/freshrss/is/installed/FreshRSS
su www-data -s /bin/sh -c 'php ./cli/import-for-user.php --user FreshRSS_user --filename /path/to/akregator-export-2018-08-20-14-20.zip'
```

12. Back on your desktop machine, execute:

```bash
python2 akregator2freshrss_dbsync.py
```

   This script connects directly to FreshRSS database and sets per-feed and per-article settings like archive size/update interval and "is read" flag, which cannot be imported via zipfile. Finally you should see _"All done without any errors! Have fun with FreshRSS!"_, however it's not ready yet... but stay tuned. If the script finished with errors, stop and debug...

13. Force fetching all feeds in FreshRSS once. On your web server execute:

```bash
su www-data -s /bin/sh -c 'php ./app/actualize_script.php'
```

14. Back on your desktop machine, execute the same command for the second time:

```bash
python2 akregator2freshrss_dbsync.py
```

   This ensures that per-article date and article order is correct after FreshRSS has updated and fetched current articles. Now if you see the _"All done without any errors! Have fun with FreshRSS!"_, it's really the end of migration :)


#### Post-migration tasks

15. If you wish to keep Akregator around, you may start it safely now.

16. Re-enable cron task used to actualize articles in FreshRSS.

17. Log in and enjoy your FreshRSS!
