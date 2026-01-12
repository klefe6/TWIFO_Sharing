# Dropbox Material Management

A comprehensive research document management and sharing system with advanced Dropbox integration, developed by Hughes & Company LLC. This sophisticated platform provides secure access to internal research materials, intelligent document categorization, and powerful search capabilities across multiple research sources.

## Overview

The Dropbox Material Management system is a professional-grade platform that enables secure access to internal research documents through an intelligent web interface. It features advanced document categorization, full-text PDF search capabilities, and seamless Dropbox integration for research material management. The system serves as a centralized hub for accessing research from major financial institutions and research providers.

## Features

### 🚀 **Advanced Document Management**
- **Intelligent Categorization**: Automatic categorization by research provider
- **Multi-Source Integration**: Support for 30+ major financial institutions
- **Secure Access Control**: User authentication and role-based permissions
- **Document Organization**: Hierarchical folder structure and metadata

### 📊 **Powerful Search Capabilities**
- **Title Search**: Fast document title and filename search
- **Content Search**: Full-text PDF content search with keyword highlighting
- **Category Filtering**: Research provider-based document filtering
- **Advanced Filters**: Date, type, and source-based filtering options

### 🔗 **Dropbox Integration**
- **Streamlit Interface**: Modern web-based Dropbox management
- **Folder Scanning**: Automated folder structure analysis
- **Content Filtering**: Intelligent document retention and filtering
- **Batch Operations**: Bulk document processing and organization

### 🎯 **Professional Research Interface**
- **Responsive Dashboard**: Modern, mobile-friendly web interface
- **Real-time Updates**: Live document availability and status
- **Interactive Tables**: Sortable and filterable document listings
- **User Management**: Secure login and access control

## Installation

### Prerequisites
- Python 3.8+
- Dropbox API access token
- pip package manager
- Streamlit (for Dropbox management interface)

### Setup Instructions

1. **Clone the repository:**
```bash
git clone https://github.com/klefebvre6/dropbox_material.git
cd dropbox_material
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Configure Dropbox access:**
Set your Dropbox API access token in the environment or configuration file.

4. **Run the main application:**
```bash
python twifo.py
```

5. **Run the Dropbox management interface:**
```bash
streamlit run import_dropbox.py
```

6. **Access the applications:**
- Main app: `http://localhost:8050`
- Dropbox management: `http://localhost:8501`

## Project Structure

```
TWIFO_Sharing/
├── twifo.py                        # Main research directory application (25KB)
├── import_dropbox.py               # Dropbox management interface (16KB)
├── testing.py                      # Testing and development utilities (3.0KB)
├── reboot_twifo.bat               # Windows service restart script
├── reboot_import_dropbox.bat      # Dropbox interface restart script
├── dropbox_file_list.csv          # Dropbox file listing (170B)
├── requirements.txt                # Python dependencies
├── README.md                       # This documentation
└── .gitignore                      # Git ignore rules
```

## Key Components

### **twifo.py** - Main Research Directory
- **Dash Web Framework**: Modern, responsive web interface
- **Document Categorization**: Intelligent provider-based classification
- **PDF Search Engine**: Full-text content search capabilities
- **User Authentication**: Secure access control system
- **Professional UI**: Research-focused dashboard design

### **import_dropbox.py** - Dropbox Management
- **Streamlit Interface**: Modern web-based Dropbox management
- **Folder Scanning**: Automated folder structure analysis
- **Content Filtering**: Intelligent document retention rules
- **Batch Operations**: Bulk document processing capabilities

### **Research Provider Coverage**
- **Major Banks**: Bank of America, JP Morgan, Goldman Sachs, Wells Fargo
- **Investment Firms**: BlackRock, Barclays, Deutsche Bank, Morgan Stanley
- **Research Providers**: TSLombard, HighTower Research, Mizuho
- **International Banks**: HSBC, UBS, ING, RBC, Nomura
- **Regional Banks**: ANZ, BCA, BNPP, CACIB, Citi

## Usage

### **Main Research Directory**

1. **User Authentication**: Secure login with role-based access
2. **Document Search**: Search by title or full-text content
3. **Category Filtering**: Filter by research provider
4. **Document Access**: Secure download and viewing
5. **User Management**: Admin controls and access management

### **Dropbox Management Interface**

1. **Folder Selection**: Choose Current, Archives, or both
2. **Date Filtering**: Select year and month for scanning
3. **Content Rules**: Configure keep/skip filters
4. **Batch Processing**: Process multiple folders simultaneously
5. **File Organization**: Automated document categorization

### **Document Categories**

- **Bank of America (BOA_)**: Research reports and analysis
- **Goldman Sachs (GM_)**: Market insights and strategy
- **JP Morgan (JPM_)**: Economic and market research
- **BlackRock (BR_)**: Investment strategy and analysis
- **TSLombard (TSL_)**: Market commentary and analysis
- **HighTower (HT_)**: Investment research and insights

## Technical Specifications

### **Dependencies**
- **Dash**: Web framework for interactive dashboards
- **Streamlit**: Modern web app framework for data science
- **PyPDF2**: PDF text extraction and search
- **Pandas**: Data manipulation and analysis
- **Dropbox SDK**: Official Dropbox API integration

### **Port Configuration**
- **Main App Port**: 8050
- **Streamlit Port**: 8501
- **Development Mode**: Debug enabled for development
- **Host**: Localhost (127.0.0.1)

### **Performance Features**
- **Efficient Search**: Optimized PDF text extraction
- **Caching System**: Intelligent document caching
- **Real-time Updates**: Live document availability
- **Responsive Design**: Mobile-friendly interface

## Security Features

### **Access Control**
- **User Authentication**: Secure login system
- **Role-based Permissions**: Different access levels
- **Session Management**: Secure session handling
- **Audit Logging**: Comprehensive access logging

### **Data Protection**
- **Secure File Access**: Protected document downloads
- **Encrypted Storage**: Secure credential storage
- **Access Logging**: Complete audit trail
- **User Isolation**: Secure user separation

## Dropbox Integration

### **API Features**
- **Folder Scanning**: Automated folder structure analysis
- **File Metadata**: Comprehensive file information
- **Content Filtering**: Intelligent document retention
- **Batch Operations**: Efficient bulk processing

### **Management Capabilities**
- **Folder Organization**: Automated folder structure
- **Content Rules**: Configurable keep/skip filters
- **Date-based Filtering**: Time-based document management
- **File Categorization**: Automatic document classification

## Research Document Types

### **Supported Formats**
- **PDF Documents**: Research reports and analysis
- **Word Documents**: Market commentary and insights
- **PowerPoint**: Presentation materials and summaries
- **Excel Files**: Data analysis and spreadsheets

### **Content Categories**
- **Market Research**: Economic and market analysis
- **Investment Strategy**: Portfolio and strategy insights
- **Commodity Research**: Commodity market analysis
- **Economic Analysis**: Macroeconomic research
- **Regional Research**: Geographic market insights

## User Management

### **Authentication System**
- **Secure Login**: Password-based authentication
- **User Roles**: Different access levels and permissions
- **Session Management**: Secure session handling
- **Access Logging**: Comprehensive audit trail

### **User Interface**
- **Responsive Design**: Mobile-friendly interface
- **Intuitive Navigation**: Easy-to-use dashboard
- **Search Functionality**: Powerful document search
- **Category Management**: Organized document access

## Development

### **Code Structure**
- **Modular Design**: Separated concerns for maintainability
- **Clean Architecture**: Clear separation of UI and business logic
- **Error Handling**: Comprehensive error handling and logging
- **Professional Standards**: Production-ready code quality

### **Extensibility**
- **Plugin Architecture**: Easy to add new features
- **Custom Categories**: Flexible document categorization
- **Data Sources**: Pluggable data provider architecture
- **UI Components**: Reusable web components

## Testing

### **Quality Assurance**
- **Unit Testing**: Individual component testing
- **Integration Testing**: End-to-end functionality testing
- **User Acceptance Testing**: Interface validation
- **Performance Testing**: Load and response time analysis

### **Error Handling**
- **Graceful Failures**: Robust error handling and recovery
- **User Feedback**: Clear error messages and guidance
- **Fallback Mechanisms**: Alternative functionality when needed
- **Logging System**: Comprehensive error logging

## Rollup System

### **Overview**
The rollup system creates daily and weekly summaries from article summaries (JSON/TXT files only - no PDFs or OCR).

### **File Naming Conventions**
- **Daily Rollups**: `ROLLUP_DAILY_YYYYMMDD__sum.json` and `ROLLUP_DAILY_YYYYMMDD__sum.txt`
  - Example: `ROLLUP_DAILY_20260111__sum.json`
- **Weekly Rollups**: `ROLLUP_WEEKLY_YYYYMMDD__sum.json` and `ROLLUP_WEEKLY_YYYYMMDD__sum.txt`
  - Example: `ROLLUP_WEEKLY_20260106__sum.json` (Monday date)
  - Where YYYYMMDD is ISO date with no dashes

### **Daily Rollups**
Generate a daily rollup for a specific date (requires >= 3 article summaries):

```bash
python generate_rollup_clean.py daily YYYY-MM-DD
# or
python generate_rollup_clean.py daily YYYYMMDD
```

### **Weekly Rollups**
Generate a weekly rollup for a date range (defaults to Mon-Fri if only start date provided):

```bash
python generate_rollup_clean.py weekly YYYY-MM-DD [YYYY-MM-DD]
# or
python generate_rollup_clean.py weekly YYYYMMDD [YYYYMMDD]
```

### **Backfilling Rollups**
Backfill daily rollups for a date range:

```bash
python backfill_rollups.py --start YYYY-MM-DD --end YYYY-MM-DD
```

Backfill weekly rollups for Mondays in a date range:

```bash
python backfill_rollups.py --start YYYY-MM-DD --end YYYY-MM-DD --weekly
```

### **Weekly Rollup Automation**
Weekly rollups run every Monday at 12:05am ET and cover the previous Monday-Friday.

To compute the previous Mon-Fri range:
- Uses America/New_York timezone
- If today is Monday before 12:05am ET, uses the week before last
- Otherwise uses last week (Mon-Fri)

Schedule with Windows Task Scheduler:
```
Program: python.exe
Arguments: "C:\Program Files\Coding Projects\TWIFO_Sharing\run_weekly_rollup.py"
Trigger: Weekly on Mondays at 12:05am ET
```

### **Rollup Schema**
- Daily and weekly rollups share the same schema
- Only `meta.rollup_kind` and `meta.week_range` differ
- Trade ideas use timeframe buckets: `d_1_3`, `w_1_2`, `gt_2w`, `watchlist_only`
- See `rollup_schema.py` for full schema documentation

### **Validation**
Validate rollup JSON files:

```bash
python rollup_validate.py <rollup_json_file>
python rollup_validate.py --dir <directory>
```

## Configuration

### **Environment Variables**
- **Dropbox Token**: API access token for Dropbox integration
- **Database Connection**: Database configuration settings
- **File Paths**: Document storage and access paths
- **Security Settings**: Authentication and access control

### **Customization Options**
- **Document Categories**: Configurable research provider categories
- **Search Filters**: Customizable search and filtering options
- **User Permissions**: Flexible access control configuration
- **UI Themes**: Customizable interface appearance

## License

This project is proprietary to Hughes & Company LLC. All rights reserved.

## Contact

For questions, support, or collaboration opportunities:
- **Company**: Hughes & Company LLC
- **Email**: dhughes@hughesandco.ltd
- **Website**: www.hughesandco.ltd

## Disclaimer

This software is for educational and informational purposes only. It does not constitute investment advice. Access to research materials is restricted to authorized users only. The system provides secure access to internal research documents and should be used in accordance with company policies and procedures.
