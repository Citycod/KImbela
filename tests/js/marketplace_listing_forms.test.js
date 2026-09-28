const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const createSource = fs.readFileSync(
  path.resolve(__dirname, '../../templates/create_service.html'),
  'utf8',
);
const editSource = fs.readFileSync(
  path.resolve(__dirname, '../../templates/edit_service.html'),
  'utf8',
);

function extractFunction(source, name) {
  const start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `${name} must exist`);
  const bodyStart = source.indexOf('{', start);
  let depth = 0;
  for (let index = bodyStart; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1;
    if (source[index] === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, index + 1);
    }
  }
  throw new Error(`Unable to extract ${name}`);
}

function makeClassList() {
  const values = new Set();
  return {
    contains(value) { return values.has(value); },
    add(value) { values.add(value); },
    remove(value) { values.delete(value); },
    toggle(value, force) {
      if (force === undefined ? !values.has(value) : force) values.add(value);
      else values.delete(value);
    },
  };
}

function makeRuntime() {
  const serviceCard = { classList: makeClassList() };
  const productCard = { classList: makeClassList() };
  const fixedCard = { classList: makeClassList() };
  const contactCard = { classList: makeClassList() };
  const service = { value: 'service', checked: false, closest: () => serviceCard };
  const product = { value: 'digital', checked: false, closest: () => productCard };
  const fixed = { value: 'fixed', checked: true, closest: () => fixedCard };
  const contact = { value: 'contact', checked: false, closest: () => contactCard };
  const elements = {
    digitalProductFields: { classList: makeClassList() },
    serviceDurationField: { classList: makeClassList() },
    duration: { disabled: false, value: '60 minutes' },
    selectedPricingType: { textContent: '' },
    priceFields: { classList: makeClassList() },
  };
  const inputs = {
    service_type: [service, product],
    pricing_mode: [fixed, contact],
  };
  const document = {
    getElementById(id) { return elements[id] || null; },
    querySelector(selector) {
      const match = selector.match(/input\[name="([^"]+)"\]\[value="([^"]+)"\]/);
      return match ? inputs[match[1]].find(input => input.value === match[2]) : null;
    },
    querySelectorAll(selector) {
      const match = selector.match(/input\[name="([^"]+)"\]/);
      return match ? inputs[match[1]] : [];
    },
  };
  const context = { document, formState: { serviceType: null, pricingType: 'fixed' } };
  vm.runInNewContext(
    `${extractFunction(createSource, 'selectServiceType')}\n${extractFunction(createSource, 'selectPricingType')}`,
    context,
  );
  return { context, elements, fixedCard, contactCard, productCard, serviceCard, inputs };
}

test('create form requires an explicit mutually-exclusive listing type', () => {
  assert.match(
    createSource,
    /name="service_type" value="service" class="hidden" required/,
  );
  assert.doesNotMatch(
    createSource,
    /name="service_type" value="service"[^>]*checked/,
  );
  assert.equal(
    (createSource.match(/<input[^>]+name="service_type"/g) || []).length,
    2,
  );
  assert.match(createSource, /serviceType: null/);
  assert.match(createSource, /Please choose Service or Product/);
});

test('listing type switches both directions without changing pricing mode', () => {
  const runtime = makeRuntime();

  runtime.context.selectServiceType('digital');
  assert.equal(runtime.inputs.service_type[1].checked, true);
  assert.equal(runtime.productCard.classList.contains('selected'), true);
  assert.equal(runtime.elements.duration.disabled, true);

  runtime.context.selectPricingType('contact');
  assert.equal(runtime.inputs.pricing_mode[1].checked, true);
  assert.equal(runtime.contactCard.classList.contains('selected'), true);
  assert.equal(runtime.productCard.classList.contains('selected'), true);

  runtime.context.selectServiceType('service');
  assert.equal(runtime.inputs.service_type[0].checked, true);
  assert.equal(runtime.serviceCard.classList.contains('selected'), true);
  assert.equal(runtime.productCard.classList.contains('selected'), false);
  assert.equal(runtime.inputs.pricing_mode[1].checked, true);
});

test('create initialization uses the actual fixed pricing value and does not force a type', () => {
  assert.match(createSource, /selectPricingType\('fixed'\);/);
  assert.doesNotMatch(createSource, /selectPricingType\('paid'\);/);
  assert.doesNotMatch(createSource, /selectServiceType\('service'\);/);
  assert.doesNotMatch(createSource, /querySelectorAll\('\.option-card'\)/);
});

test('edit form supports changing between service and product', () => {
  assert.match(editSource, /name="service_type" value="service"/);
  assert.match(editSource, /name="service_type" value="digital"/);
  assert.match(editSource, /window\.selectServiceType = function\(type\)/);
  assert.match(editSource, /syncServiceType\(\)/);
});

test('product preview does not label every product as digital', () => {
  assert.match(
    createSource,
    /formState\.serviceType === 'service' \? 'Service' : 'Product'/,
  );
  assert.doesNotMatch(
    createSource,
    /formState\.serviceType === 'service' \? 'Listing' : 'Digital Product'/,
  );
  assert.match(
    createSource,
    /document\.getElementById\('digitalFile'\)\?\.files\?\.length \? 'Digital' : 'Physical'/,
  );
});

test('create form inline scripts are syntactically valid', () => {
  const scripts = [...createSource.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
  assert.ok(scripts.length > 0);
  scripts.forEach((match, index) => {
    assert.doesNotThrow(
      () => new vm.Script(match[1]),
      `inline script ${index + 1} must parse`,
    );
  });
});
