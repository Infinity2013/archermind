#coding=utf-8
import hashlib
import os
import re
import signal
import sqlite3
import subprocess
import sys
from argparse import ArgumentParser

from BeautifulSoup import BeautifulSoup
from selenium import webdriver

web_addr = "http://exam.archermind.com/TCExam/public/code/index.php"
name = ""
passwd = ""

pid = -1


def md5(content):
    return hashlib.md5(" ".join(content)).hexdigest()


class question(object):
    def __init__(self, content, ans):
        self.content = []
        for line in content:
            t = line.encode('utf-8').strip()
            # strip tab and space
            t = t.replace('\t', '')
            t = t.replace(' ', '')
            self.content.append(t)
        self.ans = ans
        self._md5 = ""
        self._str = ""

    @property
    def md5(self):
        if self._md5 == "":
            self._md5 = md5(self.content)
        return self._md5

    def __str__(self):
        if self._str == "":
            self._str = "md5: %s\n%s\nans: %s" % (self.md5, "\n".join(self.content), " ".join(self.ans))
        return self._str

    def insert_to_db(self, cur):
        cur.execute('select * from exam where md5="%s"' % self._md5)
        if cur.fetchone() is not None:
            return
        cmd = "insert into exam (md5, content, ans) values('%s', '%s', '%s')" % \
            (self._md5, "\n".join(self.content), " ".join(self.ans))
        cur.execute(cmd)


def parse_ans(name):
    question_list = []
    node_list = []
    with open(name, "r") as f:
        src = "\n".join(f.readlines())
        soup = BeautifulSoup(src)
        for node in soup.findAll("li"):
            if node.find("strong") is not None:
                node_list.append(node)
        for node in node_list:
            start, end = 0, 0
            # parse content
            for i in xrange(len(node.contents)):
                t = str(node.contents[i])
                if "strong" in t:
                    start = i
                elif 'ol class="answer"' in t:
                    end = i
                content = []
            for i in xrange(start, end):
                if "<br />" in str(node.contents[i]):
                    content.append((node.contents[i + 1]).strip())
            # parse ans
            ans = []
            for right_ans in node.findAll("acronym", attrs={'class': 'onbox'}):
                ans.append(str(right_ans.nextSibling))
            q = question(content, ans)
            question_list.append(q)
    return question_list


def init_db():
    db = "%s/archermind_exam.db" % sys.path[0]
    try:
        conn = sqlite3.connect(db)
    except:
        print "Failed to connect db"
        sys.exit(1)
    return conn


def next_question(driver):
    elem = driver.find_element_by_name("nextquestion")
    elem.click()


def click_anwsers(driver, ans_list):
    ans = ""
    if len(ans_list) == 1:
        elems = driver.find_elements_by_xpath("//li/label[@for]")
        for elem in elems:
            node_id = elem.get_attribute("for")
            if re.findall(r'answerid_[1-9]\d*', node_id) != []:
                if elem.text in ans_list:
                    ans = elem.parent.find_element_by_xpath("//li/input[@type='radio'][@id='%s']" % node_id)
                    if ans is not None:
                        ans.click()
                        break
    else:
        elems = driver.find_elements_by_xpath('//li')
        for elem in elems:
            spans = elem.find_elements_by_tag_name('span')
            if len(spans) == 3:
                if elem.text.split()[3] in ans_list:
                    radio = elem.find_element_by_xpath('.//input[@type="radio"][@value="1"]')
                    radio.click()
        next_question(driver)


def summit(driver):
    elem = driver.find_element_by_xpath('//input[@type="submit"][@name="terminatetest"][@id="terminatetest"]')
    elem.click()


def find_answer(driver, cur):
    elem = driver.find_element_by_xpath("//div[@class='tcecontentbox']")
    content = elem.text.splitlines()
    end = 0
    for i in xrange(1, len(content)):
        if re.match(r'^[A-Z].*', content[i]) == None:
            end = i
            break
    for i in xrange(end):
        t = content[i].encode('utf-8').strip()
        # strip tab and space
        t = t.replace('\t', '')
        t = t.replace(' ', '')
        content[i] = t
    content_md5 = md5(content[0:end])
    cur.execute("select * from exam where md5='%s'" % content_md5)
    result = cur.fetchone()
    if result is None:
        return []
    ans = result[2].split()
    return ans


def login():
    driver = webdriver.Firefox()
    driver.get(web_addr)
    elem = driver.find_element_by_name("xuser_name")
    elem.send_keys(name)
    elem = driver.find_element_by_name("xuser_password")
    elem.send_keys(passwd)
    elem = driver.find_element_by_name("login")
    elem.click()
    y = 0
    for node in driver.find_elements_by_xpath("//a[@href]"):
        if u"年信息安全考试" in node.text:
            y = node.rect['y']
            break
    button = ""
    for node in driver.find_elements_by_xpath("//a[@class='buttonblue']|//a[@class='xmlbutton']|//a[@class='buttongreen']"):
        if abs(node.rect['y'] - y) < 10:
            button = node
            break
    if button.get_attribute('class') == 'buttonblue':
        button.click()
        driver.find_element_by_xpath("//a[@class='xmlbutton']").click()
    else:
        button.click()
    return driver


def kill_server():
    ps = subprocess.Popen("ps -aux | grep selenium-server-standalone", shell=True, stdout=subprocess.PIPE).communicate()[0].splitlines()
    for i in xrange(len(ps)):
        if ps[i].strip() != "":
            pid = ps[i].split()[1]
            os.system("kill %s" % pid)


def main():
    p = ArgumentParser(usage='xxxx.py [-u xxxx.html]', description='Author wxl')
    p.add_argument('-u', dest='update_database', default="", help='update the database')
    a = p.parse_known_args(sys.argv)
    update_database = a[0].update_database

    conn = init_db()
    cur = conn.cursor()
    if update_database != "":
        question_list = parse_ans(update_database)
        for question in question_list:
            question.insert_to_db(cur)
        conn.commit()
        return
    subprocess.Popen('java -jar selenium-server-standalone-2.48.2.jar', shell=True)
    driver = login()
    for i in xrange(40):
        ans = find_answer(driver, cur)
        click_anwsers(driver, ans)
    os.killpg(pid, signal.SIGTERM)


if __name__ == '__main__':
    try:
        main()
    except:
        kill_server()
