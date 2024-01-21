import json
from dataclasses import dataclass

@dataclass
class Platform:
    name: str

class BuildJob:
    pass

@dataclass
class BuildJob:
    name: str
    dependencies = list[ BuildJob ]

@dataclass
class BuildGroup:
    name: str
    jobs = list[ BuildJob ]

class BuildPipeline:
    def add_build_group( self, platform: Platform, build_group_name: str ) -> BuildGroup:
        build_group = BuildGroup( build_group_name )

        if platform in self.pipelines:
            self.pipelines[ platform ].append( build_group )
        else:
            self.pipelines[ platform ] = [ BuildGroup ]

        return build_group

    pipelines: dict[ Platform, list[ BuildGroup ] ] = {}
 
with open( 'BuildGraph.json' ) as json_file:
    data = json.load( json_file )

    build_pipeline = BuildPipeline()
 
    for group in data[ 'Groups' ]:
        platform = group[ 'Agent Types' ][ 0 ]

        build_group = build_pipeline.add_build_group( platform, group[ 'Name' ] ) 

        for node in group[ 'Nodes' ]:
            node_name = node[ 'Name' ]
            dependencies = node[ 'DependsOn' ].split( ';' )

        