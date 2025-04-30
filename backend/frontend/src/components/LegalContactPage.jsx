// src/components/LegalContactPage.jsx

import React from 'react';

const tiles = [
  {
    title: 'Terms and Conditions',
    content: `By using this platform, you agree to abide by our terms and conditions. 
    Please use the platform responsibly. We reserve the right to modify or terminate services at any time.`,
  },
  {
    title: 'Cancellations and Refunds',
    content: `No cancellations or refunds are permitted after a transaction is completed. 
    Please review your order carefully before proceeding.`,
  },
  {
    title: 'Privacy Policy',
    content: `We are committed to protecting your privacy. Your personal data is handled 
    securely and is not shared with third parties without consent. Please refer to our full privacy policy for details.`,
  },
  {
    title: 'Contact Us',
    content: (
      <div className="space-y-2 text-sm">
        <p>
          <strong>Email:</strong>{' '}
          <a href="mailto:qnagenai@gmail.com" className="text-blue-600 underline">
            qnagenai@gmail.com
          </a>
        </p>
        <p>
          <strong>Phone:</strong>{' '}
          <a href="tel:+918050903058" className="text-blue-600 underline">
            +91 8050903058
          </a>
        </p>
        <p><strong>Address:</strong> Near Padma Hospital, Devaraj Nagar, Terdal - 587315, Karnataka</p>
        <a
          href="https://wa.me/918050903058"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600"
        >
          📲 Chat on WhatsApp
        </a>
      </div>
    ),
  },
];

const LegalContactPage = () => {
  return (
    <div className="container my-5 pt-5 px-3 md:px-0" style={{ minHeight: '100vh' }}>
      <h1 className="text-3xl font-bold mb-6 text-center">Legal & Contact Information</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {tiles.map((tile, index) => (
          <div
            key={index}
            className="p-6 border rounded shadow hover:shadow-lg transition duration-200 bg-white break-words"
          >
            <h2 className="text-xl font-semibold mb-3">{tile.title}</h2>
            <div className="text-gray-700 text-sm space-y-2">{tile.content}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default LegalContactPage;
