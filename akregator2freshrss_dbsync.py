#!/usr/bin/python2
# coding=utf-8
# py2, cause metakit library is pretty much dead and does not support py3...

from __future__ import print_function, division

import sys
sys.dont_write_bytecode = True
import bisect
import os

import MySQLdb
import MySQLdb.constants.CLIENT

# git clone https://github.com/jnorthrup/metakit.git
# cd metakit/builds
# ../unix/configure
# make -j4
# cd ../python
# python2 setup.py build -b ../builds
# python2 setup.py install --user
# OR... "emerge metakit" ;-)
import metakit


from a2f_config import ak_archive_path, frdb_host, frdb_user, frdb_pass, frdb_name, frdb_table_prefix
from akregator2zip import uesc, read_feeds_opml, extract_feed_nodes


frdb = MySQLdb.connect(host=frdb_host, user=frdb_user, passwd=frdb_pass, db=frdb_name,
                       client_flag=MySQLdb.constants.CLIENT.FOUND_ROWS)


def update_feed_settings(feedlist):
    """Moves feed settings (archive size/update interval) from Akregator archive to FreshRSS DB."""
    def outline_to_feed_updatedata(outline):
        # keep_history = "Minimum number of articles to keep";
        # -2: global settings; -1: unlimited archive; 0+: specified value
        archive_mode = outline.get('archiveMode', 'globalDefault')
        if archive_mode == 'globalDefault':
            keep_history = -2
        elif archive_mode == 'keepAllArticles':
            keep_history = -1
        elif archive_mode == 'disableArchiving':
            keep_history = 0
        elif archive_mode == 'limitArticleNumber':
            # limit to allowed values
            possible_values = [10, 50, 100, 500, 1000, 5000, 10000]
            idx = bisect.bisect_left(possible_values, int(outline.get('maxArticleNumber')))
            try:
                keep_history = possible_values[idx]
            except IndexError:
                keep_history = -1  # more than 10k - keep all
        else:  # 'limitArticleAge' (unsupported by FreshRSS) or unknown
            keep_history = -2

        # ttl = "Do not automatically refresh more often than" [s]
        # 0: global setting; 900+: refresh period in seconds; -900: mute (original refresh period negated)
        ttl = 0  # fetch_interval==0 or useCustomFetchInterval==false - use global
        if outline.get('useCustomFetchInterval', 'false').lower() == 'true':
            fetch_interval = int(outline.get('fetchInterval', '0'))
            if fetch_interval < 0:    # -1: "never" (use 1d + "mute")
                ttl = -86400
            elif fetch_interval > 0:  # positive: interval in minutes (convert to seconds)
                ttl = fetch_interval * 60
                possible_values = [900, 1200, 1500, 1800, 2700, 3600, 5400, 7200, 10800,           # 15min ... 3h
                                   14400, 18800, 21600, 25200, 28800, 36000, 43200, 64800, 86400,  # 4h ... 1d
                                   129600, 172800, 259200, 345600, 432000, 518400, 604800,         # 2d ... 1wk
                                   1209600, 1814400, 2419200, 2629744]                             # 2wk ... 1mo
                idx = bisect.bisect_left(possible_values, ttl)
                # instead of clamping to larger values like we do for keep_history,
                # for ttl we chose nearest allowed integer.
                closest_matches = possible_values[max(0, idx-1) : idx+1]
                if len(closest_matches) == 1:
                    ttl = closest_matches[0]
                else:
                    m1, m2 = closest_matches
                    ttl = m1 if (ttl - m1) < (m2 - ttl) else m2

        if outline.get('markImmediatelyAsRead', 'false').lower() == 'true':
            attributes = '{"read_upon_reception":true}'
        else:
            attributes = '[]'

        return (keep_history, ttl, attributes, uesc(outline.get('xmlUrl')))

    c = frdb.cursor()
    feed_table = frdb_table_prefix + 'feed'
    updates, fails = 0, 0
    for category, outlines in feedlist.iteritems():
        for outline in outlines:
            data = outline_to_feed_updatedata(outline)
            found_rows = c.execute('UPDATE ' + feed_table + ' SET keep_history=%s, ttl=%s, attributes=%s WHERE url=%s', data)
            if found_rows:
                print(u"Successfully updated feed settings for {}".format(outline.get('title')))
                updates += 1
            else:
                # not found? FreshRSS maybe updated feed url. Retry by feed title and website url
                found_rows = c.execute('UPDATE ' + feed_table + ' SET keep_history=%s, ttl=%s, attributes=%s WHERE name=%s AND website=%s',
                                       data[:3] + (uesc(outline.get('title')), uesc(outline.get('htmlUrl'))))
                if found_rows:
                    print(u"Successfully updated (with retry) feed settings for {}".format(outline.get('title')))
                    updates += 1
                else:
                    print(u"ERROR: failed to update feed settings for {} (feed not found in FreshRSS database)".format(outline.get('title')))
                    fails += 1

    c.close()
    frdb.commit()
    print("Feed settings applied; {} feeds updated, {} feeds failed".format(updates, fails))
    return fails


def update_article_status(feedlist):
    """Sets feed articles read/unread and favorite flag in FreshRSS MySQL database."""
    c = frdb.cursor()
    entry_table = frdb_table_prefix + 'entry'
    feed_table = frdb_table_prefix + 'feed'
    updates, fails = 0, 0

    def update_feed_articles(outline, feed_id):
        articles = []
        feed_url = outline.get('xmlUrl')
        html_url = outline.get('htmlUrl')
        feed_title = outline.get('title')
        feed_file = feed_url.replace(':', '_').replace('/', '_') + '.mk4'
        fdb = metakit.storage(os.path.join(ak_archive_path, feed_file), 0)
        updates, fails = 0, 0
        for a in fdb.getas(fdb.description()):
            # Akregator status bits: Deleted = 0x01, Trash = 0x02, New = 0x04, Read = 0x08, Keep = 0x10
            if a.status & 0x3:
                continue  # skip articles marked as "deleted" or "thrash"
            is_read = bool(a.status & 0x08)
            is_fav = bool(a.status & 0x10)
            guid = a.link if a.guid.startswith('hash:') else a.guid
            found_rows = c.execute('UPDATE ' + entry_table + ' SET date=%s, is_read=%s, is_favorite=%s WHERE id_feed=%s AND guid=%s',
                                   (a.pubDate, is_read, is_fav, feed_id, uesc(guid)))
            if found_rows:
                updates += 1
            else:
                fails += 1

        if fails:
            print(u"ERROR: failed to update {} articles in {} (article not found in FreshRSS database)".format(fails, feed_title))
        else:
            print(u"Successfully updated {} articles in feed {}".format(updates, feed_title))

        c.execute('SELECT COUNT(id) FROM ' + entry_table + ' WHERE id_feed=%s AND is_read=0', (feed_id,))
        return updates, fails, c.fetchone()[0]

    for category, outlines in feedlist.iteritems():
        for outline in outlines:
            c.execute('SELECT id FROM ' + feed_table + ' WHERE url=%s', (uesc(outline.get('xmlUrl')),))
            row = c.fetchone()
            if not row:
                # not found? FreshRSS maybe updated feed url. Retry by feed title and website url
                c.execute('SELECT id FROM ' + feed_table + ' WHERE name=%s AND website=%s',
                          (uesc(outline.get('title')), uesc(outline.get('htmlUrl'))))
                row = c.fetchone()
                if not row:
                    print(u"ERROR: feed '{}' ({}) not found in FreshRSS database".format(outline.get('title'), outline.get('xmlUrl')))
                    fails += 1
                    continue

            feed_id = row[0]
            stats = update_feed_articles(outline, feed_id)
            updates += stats[0]
            fails += stats[1]
            c.execute('UPDATE ' + feed_table + ' SET cache_nbUnreads=%s WHERE id=%s', (stats[2], feed_id))
            frdb.commit()

    c.close()
    frdb.commit()
    print("Article status updated; {} articles updated, {} articles failed".format(updates, fails))
    return fails


def fix_article_order():
    """Changes article ID values in order to make FreshRSS display them chronologically in category/mainstream view."""
    c = frdb.cursor()
    entry_table = frdb_table_prefix + 'entry'
    updates, fails = 0, 0

    # get what needs to be changed
    c.execute('SELECT id, date FROM ' + entry_table + ' WHERE id NOT BETWEEN date*1000000 AND ((date+1)*1000000)-1')
    oldidmap = {row[0]: row[1] for row in c}   # id -> date
    print("Order fix: {} entries require ID update".format(len(oldidmap)))

    # calculate new IDs
    idremap = {}  # newid -> oldid
    for oldid, date in oldidmap.iteritems():
        for i in xrange(1000000):
            newid = date * 1000000 + (oldid + i) % 1000000
            # for simplicity we require that new id is not yet taken at all
            # (so we don't have to resolve cascade/circular updates when for example
            # we do old1->new1 and old2->new2, but it happens that new1==old2 or maybe
            # even worse new1==old2 and new2==old1)
            if newid not in oldidmap and newid not in idremap:
                # success; not conflicting new ID found
                idremap[newid] = oldid
                break
        else:
            # very unlikely, but all IDs taken?
            print("ERROR: failed to generate new ID for id={} date={}: all possible IDs taken".format(oldid, date))
            fails += 1

    # push changes to DB
    for i, (newid, oldid) in enumerate(idremap.iteritems(), start=1):
        found_rows = c.execute('UPDATE ' + entry_table + ' SET id=%s WHERE id=%s', (newid, oldid))
        if found_rows:
            updates += 1
        else:
            # WTF?
            print("ERROR: failed to update ID {} -> {}: row not found (have you stopped FreshRSS updater?)".format(oldid, newid))
            fails += 1

        # commit and print status once a while
        if (i % 1000) == 0:
            frdb.commit()
            print("Updated {:6d} article IDs  ({:.2f}% done)".format(i, 100.0 * i / len(idremap)))

    c.close()
    frdb.commit()
    print("Article order updated; {} article IDs changed, {} failed".format(updates, fails))
    return fails


def main():
    fails = 0
    if len(sys.argv) < 2 or sys.argv[1] != 'order-only':
        opml = read_feeds_opml()
        feedlist = extract_feed_nodes(opml)

        fails += update_feed_settings(feedlist)
        print("-" * 80)

        fails += update_article_status(feedlist)
        print("-" * 80)

    fails += fix_article_order()

    print("-" * 80)
    if fails:
        print("All done; {} errors encountered!".format(fails))
        print("Have you imported the zip file and stopped both Akregator/FreshRSS updating process?")
    else:
        print("All done without any errors! Have fun with FreshRSS!")


if __name__ == '__main__':
    main()
