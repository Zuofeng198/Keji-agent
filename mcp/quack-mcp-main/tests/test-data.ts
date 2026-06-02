// Test data utilities for creating in-memory CSV content

export const createTestCSVContent = (data: Record<string, any>[]): string => {
  if (data.length === 0) return '';
  
  const headers = Object.keys(data[0]);
  const headerRow = headers.join(',');
  
  const dataRows = data.map(row => {
    return headers.map(header => {
      const value = row[header];
      // Handle values that contain commas or quotes
      if (typeof value === 'string' && (value.includes(',') || value.includes('"'))) {
        return `"${value.replace(/"/g, '""')}"`;
      }
      return value;
    }).join(',');
  });
  
  return [headerRow, ...dataRows].join('\n');
};

export const sampleCreditCardData = [
  { Date: '2025-05-01', Name: 'STARBUCKS STORE #123', Amount: -4.95 },
  { Date: '2025-05-01', Name: 'KROGER FUEL CENTER', Amount: -45.20 },
  { Date: '2025-05-02', Name: 'AMAZON.COM', Amount: -29.99 },
  { Date: '2025-05-03', Name: 'TARGET STORE T-1234', Amount: -67.45 },
  { Date: '2025-05-03', Name: 'WHITS FROZEN CUSTARD', Amount: -22.06 },
  { Date: '2025-05-04', Name: 'GOOGLE *YouTubePremium', Amount: -15.32 },
  { Date: '2025-05-05', Name: 'APPLE.COM/BILL', Amount: -9.99 },
  { Date: '2025-05-05', Name: 'AHA INDIAN GRILL', Amount: -64.65 },
  { Date: '2025-05-06', Name: 'KROGER STORE #456', Amount: -89.32 },
  { Date: '2025-05-07', Name: 'SPEECH THERAPY SERVICE', Amount: -80.00 }
];

export const sampleTransactionData = [
  { id: 1, amount: 100.50, description: 'Payment received', type: 'credit' },
  { id: 2, amount: -25.00, description: 'Coffee shop', type: 'debit' },
  { id: 3, amount: -1500.00, description: 'Rent payment', type: 'debit' },
  { id: 4, amount: 50.00, description: 'Refund', type: 'credit' },
  { id: 5, amount: -12.99, description: 'Subscription fee', type: 'debit' },
];

export const sampleAnomalyData = [
  { id: 1, value: 10, category: 'normal' },
  { id: 2, value: 15, category: 'normal' },
  { id: 3, value: 12, category: 'normal' },
  { id: 4, value: 9999, category: 'outlier' }, // Statistical outlier
  { id: 5, value: 11, category: 'normal' },
  { id: 6, value: null, category: 'normal' }, // Null value
  { id: 7, value: 13, category: 'normal' },
  { id: 8, value: 10, category: 'duplicate' }, // Duplicate value
  { id: 9, value: 10, category: 'duplicate' }, // Duplicate value
  { id: 10, value: 14, category: 'normal' },
];