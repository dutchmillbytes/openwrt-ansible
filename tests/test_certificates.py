import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

os.environ.setdefault('ANSIBLE_LOCAL_TEMP','/tmp/ansible-tests')
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar
try:
    from ansible.template import trust_as_template
except ImportError:  # ansible-core 2.18
    trust_as_template = lambda value: value

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('openssl'),'OpenSSL required')
class CertificateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.cert=self.root/'cert.pem'
        self.check=ROOT/'roles/acme/files/check-certificate.sh'

    def tearDown(self):self.temp.cleanup()

    def issue(self,sans):
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(self.root/'key.pem'),'-out',str(self.cert),'-days','2','-subj','/CN=ap-1.nl.vanoijen.home','-addext','subjectAltName='+sans],check=True,capture_output=True)

    def check_cert(self,seconds=3600):
        return subprocess.run(['/bin/sh',str(self.check),str(self.cert),str(seconds),'ap-1.nl.vanoijen.home','ap-1'],capture_output=True).returncode

    def test_missing_certificate(self):self.assertEqual(self.check_cert(),1)

    def test_fqdn_only_requires_reissuance(self):
        self.issue('DNS:ap-1.nl.vanoijen.home');self.assertEqual(self.check_cert(),1)

    def test_matching_sans_and_lifetime(self):
        self.issue('DNS:ap-1,DNS:ap-1.nl.vanoijen.home');self.assertEqual(self.check_cert(),0)
        self.assertEqual(self.check_cert(3*86400),1)

    def test_extra_san_requires_reissuance(self):
        self.issue('DNS:ap-1.nl.vanoijen.home,DNS:ap-1,DNS:old-name');self.assertEqual(self.check_cert(),1)

    def test_malformed_certificate(self):
        self.cert.write_text('invalid');self.assertEqual(self.check_cert(),1)

    def test_failed_reissue_restores_previous_state(self):
        self._reissue_failure('exit 1', '/bin/true')

    def test_failed_post_issue_validation_restores_previous_state(self):
        self._reissue_failure('exit 0', '/bin/false')

    def _reissue_failure(self,client_result,validation):
        state=self.root/'state';domain=state/'ap-1.nl.vanoijen.home_ecc';domain.mkdir(parents=True)
        (domain/'old-cert').write_text('previous certificate')
        bindir=self.root/'bin';bindir.mkdir()
        (bindir/'uci').write_text('#!/bin/sh\nprintf "%s\\n" '+shlex.quote(str(state))+'\n');(bindir/'uci').chmod(0o700)
        fake=self.root/'acme-client'
        fake.write_text('#!/bin/sh\nprintf new > '+shlex.quote(str(domain/'old-cert'))+'\n'+client_result+'\n');fake.chmod(0o700)
        template=(ROOT/'roles/acme/templates/reissue.sh.j2').read_text()
        variables={'acme_section_id':'main','acme_main_domain':'ap-1.nl.vanoijen.home','acme_issue_spec':{'key_type':'ec256','domains':['ap-1.nl.vanoijen.home','ap-1'],'acme_server':'https://ca.test/directory','days':10},'acme':{'account_email':'test@example.test'},'acme_certificate_check_cmd':validation}
        script=Templar(loader=DataLoader(),variables=variables).template(trust_as_template(template))
        self.assertNotIn("{{",script)
        self.assertNotIn("{%",script)
        script=script.replace('/usr/lib/acme/client/acme.sh',str(fake)).replace('/var/run/acme/challenge',str(self.root/'challenge')).replace('/tmp/ansible-acme-backup.',str(self.root/'backup.'))
        proc=subprocess.run(['/bin/sh','-c',script],env=dict(os.environ,PATH=str(bindir)+':'+os.environ['PATH']),capture_output=True,text=True)
        self.assertNotEqual(proc.returncode,0)
        self.assertEqual((domain/'old-cert').read_text(),'previous certificate',proc.stderr)

if __name__=='__main__':unittest.main()
