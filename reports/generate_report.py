from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Create document
doc = Document()

# Title
title = doc.add_heading('Traffic Signal Control: AI vs Rule-Based Comparison', 0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER

# Intro
doc.add_paragraph('Analysis of simulation results comparing the Agentic Brain (LLM-based) controller against the Rule-Based Traffic Agent for a 4-phase intersection.')

# Main comparison table
doc.add_heading('Performance Comparison', level=1)

table = doc.add_table(rows=6, cols=5)
table.style = 'Table Grid'

# Header row
header_cells = table.rows[0].cells
header_cells[0].text = 'Metric'
header_cells[1].text = 'Traffic Agent'
header_cells[2].text = 'Agentic Brain'
header_cells[3].text = 'Difference'
header_cells[4].text = 'Winner'

# Data rows
data = [
    ('Vehicles Processed', '1,754', '1,776', '+22 (+1.3%)', 'AI'),
    ('Avg Travel Time', '104.37s', '77.34s', '-27s (-26%)', 'AI'),
    ('Avg Delay', '65.10s', '41.41s', '-24s (-36%)', 'AI'),
    ('Avg Speed', '4.39 m/s', '4.92 m/s', '+0.53 (+12%)', 'AI'),
    ('Throughput', '1,802 veh/hr', '1,801 veh/hr', '~Same', 'Tie'),
]

for i, row_data in enumerate(data):
    row = table.rows[i + 1].cells
    for j, cell_text in enumerate(row_data):
        row[j].text = cell_text

# Key Insights
doc.add_heading('Key Insights', level=1)

doc.add_heading('1. Agentic Brain significantly reduces delays', level=2)
doc.add_paragraph('The LLM-based controller cut average delay by 36% (65s → 41s). This is the most important metric for traffic optimization.')

doc.add_heading('2. Travel times improved by ~27 seconds per vehicle', level=2)
doc.add_paragraph('Across 1,776 vehicles, that\'s approximately 13 hours of cumulative time saved in a 1-hour simulation.')

doc.add_heading('3. Throughput is nearly identical', level=2)
doc.add_paragraph('Both systems processed ~1,800 veh/hour. The AI isn\'t moving more cars through — it\'s moving them faster with less waiting.')

doc.add_heading('4. Occupancy is more balanced with AI', level=2)
doc.add_paragraph('The rule-based agent caused congestion buildup on the South approach (12.76% occupancy). The AI distributed traffic more evenly across all directions (8-9% each).')

# Occupancy table
occ_table = doc.add_table(rows=3, cols=3)
occ_table.style = 'Table Grid'
occ_table.rows[0].cells[0].text = 'Direction'
occ_table.rows[0].cells[1].text = 'Traffic Agent'
occ_table.rows[0].cells[2].text = 'Agentic Brain'
occ_table.rows[1].cells[0].text = 'South (loop_S_0)'
occ_table.rows[1].cells[1].text = '12.76%'
occ_table.rows[1].cells[2].text = '8.95%'
occ_table.rows[2].cells[0].text = 'Other lanes'
occ_table.rows[2].cells[1].text = '8-9%'
occ_table.rows[2].cells[2].text = '8-9%'

# Why the difference
doc.add_heading('Why the Difference?', level=1)

doc.add_paragraph('Traffic Agent uses simple hysteresis (switch if >2 cars difference) — reactive but not predictive.')
doc.add_paragraph('Agentic Brain can reason about all 4 directions simultaneously and make context-aware decisions.')

# Conclusion
doc.add_heading('Conclusion', level=1)
p = doc.add_paragraph()
p.add_run('Bottom Line: ').bold = True
p.add_run('The AI controller achieves the same throughput with significantly less delay, making it more efficient for the same infrastructure.')

# Save
doc.save('d:/MS Thesis Imp/basic/simulation_results_analysis.docx')
print("Document saved to: d:/MS Thesis Imp/basic/simulation_results_analysis.docx")
