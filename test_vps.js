const http = require('http');

const req = http.request('http://localhost:5000/profile/1', (res) => {
  let data = '';
  res.on('data', (chunk) => { data += chunk; });
  res.on('end', () => {
    if (data.includes('Dropdown.init()')) {
      console.log('YES');
    } else {
      console.log('NO');
    }
  });
});

req.on('error', (e) => { console.error(`problem with request: ${e.message}`); });
req.end();
