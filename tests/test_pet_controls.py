"""Exercise the drawer's actual DOM event bubbling in a local Chromium browser."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def chromium():
    for name in ('chromium', 'chromium-browser', 'google-chrome', 'msedge'):
        if path := shutil.which(name):
            return path
    for env, relative in (
        ('ProgramFiles', 'Google/Chrome/Application/chrome.exe'),
        ('ProgramFiles(x86)', 'Microsoft/Edge/Application/msedge.exe'),
    ):
        if folder := os.environ.get(env):
            path = Path(folder) / relative
            if path.is_file():
                return str(path)
    return None


SCENARIO = """
const mount = document.querySelector('main');
const status = document.querySelector('output');
const actions = [];
const api = async (path, body) => {
  if (path === '/api/ai/status') return {text: null};
  if (path === '/api/pet/interact') actions.push(body.action);
  return {mood:'calm', memories:[]};
};
try {
  await mountPet(mount, {api, escape: String});
  const pet = mount.querySelector('.zj-pet');
  const drawer = pet.querySelector('section');
  const initial = pet.dataset.edge;
  pet.querySelector('.zj-pet-launch').click();
  for (const selector of ['textarea', 'label.zj-pet-question', 'summary', '[data-tickle]',
                          '[data-action="wave"]', '[data-action="stretch"]', '[data-action="rest"]']) {
    const control = drawer.querySelector(selector);
    if (!control) throw Error('missing ' + selector);
    control.click();
    await Promise.resolve();
    if (pet.dataset.edge !== initial) throw Error('unexpected switch on ' + selector);
  }
  if (actions.join(',') !== 'pat,wave,stretch,rest') throw Error('actions: ' + actions);
  const swap = [...drawer.querySelectorAll('button')].find(b => b.textContent === '换边');
  swap.click();
  if (pet.dataset.edge === initial) throw Error('explicit switch failed');
  drawer.querySelector('.zj-pet-close').click();
  if (!drawer.hidden || pet.dataset.edge === initial) throw Error('close changed position');
  status.textContent = 'PASS';
} catch (error) {
  status.textContent = 'FAIL ' + error.message;
}
"""


class PetControlTest(unittest.TestCase):
    def test_only_swap_button_moves_open_drawer(self):
        browser = chromium()
        if not browser:
            self.skipTest('A local Chrome, Edge or Chromium browser is required')
        module = (ROOT / 'web' / 'pet.js').read_text(encoding='utf-8').replace('export async function mountPet', 'async function mountPet', 1)
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            page = work / 'test.html'
            page.write_text('<meta charset="utf-8"><main></main><output></output>'
                            '<script>' + module + '\n;(async () => {' + SCENARIO + '})();</script>', encoding='utf-8')
            run = subprocess.run(
                [browser, '--headless', '--disable-gpu', '--no-first-run',
                 '--disable-extensions', '--disable-background-networking',
                 '--user-data-dir=' + str(work / 'browser'), '--virtual-time-budget=3000', '--dump-dom', page.as_uri()],
                capture_output=True, encoding='utf-8', errors='replace', timeout=30,
            )
            self.assertEqual(run.returncode, 0, run.stderr[-800:])
            start = run.stdout.find('<output>')
            self.assertTrue(run.stdout[start:].startswith('<output>PASS</output>'), run.stdout[start:start+100])
