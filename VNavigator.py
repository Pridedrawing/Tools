# * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
# *  VNavigator - The RenPy Visual Novel story visualization tool           * 
# * ----------------------------------------------------------------------- *
# *  This tool parses RenPy story files (.rpy) for label/jump statements    *
# *  and creates a .graphml flowchart file readable by yEd Graph Editor.    *
# *  Create a new folder inside the RenPy game's "game" directory, copy     *
# *  this file (VNavigator.py) into it and execute it.                      *
# * ----------------------------------------------------------------------- *
# *  Version history:                                                       *
# *  24 Jan 2023 V0.9 First version                                         *
# * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *

# Import required modules:
import os
from pathlib import Path
import glob

# Get required directories/folders:
cwd = os.getcwd()               # Where VNavigator files are stored
path = Path(cwd) 
pwd = path.parent.absolute()    # Where .rpy files are stored
folder = format(cwd)
folder = folder[folder.rfind('\\')+1:] # Current folder name
atom = format(pwd)              # Plain-text path of Atom editor 
atom = atom[:atom.find("renpy\\")+6]+'atom\\atom-windows\\atom.exe'

# Print all directories:
print("Working directory: {0}".format(cwd)) 
print("Parent directory:  {0}".format(pwd)) 
print('Folder name : '+folder)
print("Atom path: "+atom) 

# Initialize variables/lists:
edges = 0                       # Global counter for edges (arrows) 
edgli = []                      # XML list of edges (arrows)
nodli = []                      # XML list of nodes (boxes)
nchek = []                      # List of labels mentioned in jumps
echek = []                      # List of labels 

# Retrieve contents of all .rpy files:
os.chdir(pwd)                   # Go to game scripts folder
extension = '*.rpy'             # RenPy game script files

for file in glob.glob(extension):
    print('File name : ' + file)

    if file == 'gui.rpy' or file == 'options.rpy' or file == 'screens.rpy':
        print('File skipped : ' + file)
        continue
        
    with open(file, 'r') as f:
        index = 0               # line counter, reset for each file
        
        lines = f.readlines()
        for line in lines:
            index += 1          # Increment line counter
            line = line.lstrip()# Remove leading spaces
            temp = line.lower() # Convert to lowercase

            if temp[:5] == 'jump ' :
                edges += 1      # Internal counter for edges/arrows
                jumpp = line[5:]# Remove the "jump" command
                jumpp = jumpp.lstrip()          # Remove leading spaces
                jumpp = jumpp[:jumpp.find("#")] # Cut off any comments
                jumpp = jumpp.rstrip()          # Remove trailing spaces
                print('  '+str(index) + ' Jump to : ' + jumpp)
                nchek.append(jumpp.lower())     # Remember labels used in jumps

                # Add edge (arrow) from-to info:
                edgli.append('    <edge id="e'+str(edges)+'" source="'+prlab.lower()+'" target="'+jumpp.lower()+'">\n')

                # Add text on edge (arrow), if any:
                if line.find("#") > 0 :             # A comment exists 
                    jucom = line[line.find("#")+2:] # Save comment after "#" sign
                    jucom = jucom.rstrip()          # Remove trailing spaces
                    print('  Jump Comment : '+jucom)
                    edgli.append('      <data key="d9">')
                    edgli.append('        <y:PolyLineEdge>')
                    edgli.append('          <y:Arrows source="none" target="standard"/>')
                    edgli.append('          <y:EdgeLabel>'+jucom+'</y:EdgeLabel>')
                    edgli.append('        </y:PolyLineEdge>')
                    edgli.append('      </data>')
                
                edgli.append('    </edge>\n')
                
            if temp[:6] == 'label ' :
                label = line[6:]                # Remove the "label" command
                label = label[:label.find(":")] # Cut off after colon
                prlab = label                   # Remember previous (from) label
                print(' '+str(index) +' Node label : ' + label) # Final label name
                
                if line.find('#') > 0:
                    title = line[line.find('#')+1:] # Extract label comment
                    title = title.lstrip()      # Remove leading spaces
                    title = title.rstrip()      # Remove trailing spaces
                    print(' '+str(index) +' Node title : ' + title)
                else:
                    title = ''
                    print(' '+str(index) +' No node title!')
                    
                if title[:1] == '-':            # Skip label if comment starts with "-" 
                    print(' '+str(index) +' Node label skipped')
                    continue                    # Do not add the node to the yEd file

                nodli.append('    <node id="'+label.lower()+'">\n') # Use label as node ID
                nodli.append('      <data key="d3" xml:space="preserve"><![CDATA['+format(cwd)+'\\'+label+'.bat]]></data>\n')
                nodli.append('      <data key="d5">\n')             # d5 = node identifier
                nodli.append('        <y:ShapeNode>\n')
                nodli.append('          <y:Geometry height="36.0" width="240.0"/>')
                nodli.append('          <y:Fill hasColor="false" transparent="false"/>')
                nodli.append('          <y:NodeLabel>'+label+' / '+file[:len(file)-4]+'\n') # Show label in node
                nodli.append(title+'</y:NodeLabel>\n')              # Show comment on 2nd line
                nodli.append('        </y:ShapeNode>\n')
                nodli.append('      </data>\n')
                nodli.append('    </node>\n')

                echek.append(label.lower())     # Collect list of labels

                # Create batch files for every label (allows opening with Atom):
                with open(format(cwd)+'\\'+label+'.bat', 'w') as g:
                    g.write('@"'+atom+'" "'+format(pwd)+'\\'+file+':'+str(index)+'"')

    # Check for any missing jump destination (label) and add if needed:
    for x in range(len(nchek)):
        if not ( nchek[x] in echek ):
            print(nchek[x]+' label not found')                

            nodli.append('    <node id="'+nchek[x]+'">\n')  # Use label as node ID
            nodli.append('      <data key="d5">\n')         # d5 = node identifier
            nodli.append('        <y:ShapeNode>\n')
            nodli.append('          <y:Geometry height="36.0" width="240.0"/>')            
            nodli.append('          <y:Fill color="#FFAAAA" transparent="false"/>')            
            nodli.append('          <y:NodeLabel>'+nchek[x]+' (!)</y:NodeLabel>\n') # Show label in node
            nodli.append('        </y:ShapeNode>\n')
            nodli.append('      </data>\n')
            nodli.append('    </node>\n')

# Write the collected data to an yEd file:

os.chdir(cwd)   # Go to working subdirectory
with open(folder+'.graphml', 'w') as f:
    # Write static header info:
    f.write('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n')
    f.write('<graphml xmlns="http://graphml.graphdrawing.org/xmlns" xmlns:java="http://www.yworks.com/xml/yfiles-common/1.0/java" xmlns:sys="http://www.yworks.com/xml/yfiles-common/markup/primitives/2.0" xmlns:x="http://www.yworks.com/xml/yfiles-common/markup/2.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:y="http://www.yworks.com/xml/graphml" xmlns:yed="http://www.yworks.com/xml/yed/3" xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns http://www.yworks.com/xml/schema/graphml/1.1/ygraphml.xsd">\n')
    f.write('  <!--Created by yEd 3.21.1-->\n')
    f.write('  <key for="port" id="d0" yfiles.type="portgraphics"/>\n')
    f.write('  <key for="port" id="d1" yfiles.type="portgeometry"/>\n')
    f.write('  <key for="port" id="d2" yfiles.type="portuserdata"/>\n')
    f.write('  <key attr.name="url" attr.type="string" for="node" id="d3"/>\n')
    f.write('  <key attr.name="description" attr.type="string" for="node" id="d4"/>\n')
    f.write('  <key for="node" id="d5" yfiles.type="nodegraphics"/>\n')
    f.write('  <key for="graphml" id="d6" yfiles.type="resources"/>\n')
    f.write('  <key attr.name="url" attr.type="string" for="edge" id="d7"/>\n')
    f.write('  <key attr.name="description" attr.type="string" for="edge" id="d8"/>\n')
    f.write('  <key for="edge" id="d9" yfiles.type="edgegraphics"/>\n')
    f.write('  <graph edgedefault="directed" id="G">\n')

    # Add list of nodes (labels):
    for x in range(len(nodli)):
        f.write(nodli[x])

    # Add list of edges (jumps):
    for x in range(len(edgli)):
        f.write(edgli[x])

    f.write('  </graph>\n')
    f.write('</graphml>\n')

# End of program
