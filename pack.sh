#!/bin/bash

if [ -z "$1" ]; 
then
    echo "host empty"
    exit 1
fi

if [ -z "$2" ]; 
then
    echo "key empty"
    exit 1
fi

for i in $(find . -name '*.csproj'); do
    IsPackable=$(xpath -q -e '/Project/PropertyGroup/IsPackable/text()' $i | tr '[:lower:]' '[:upper:]')
    
    if [ "$IsPackable" != "TRUE" ];
    then
        continue
    fi

    ver=$(xpath -q -e '/Project/PropertyGroup/PackageVersion/text()' $i)
    name=$(xpath -q -e '/Project/PropertyGroup/PackageId/text()' $i)

    if [ -z $ver ]; 
    then
        echo "$i: version not found"
        exit 1
    fi

    if [ -z $name ]; 
    then
        echo "$i: name not found"
        exit 1
    fi

    response=$(curl --write-out '%{http_code}' --silent --output /dev/null $1/$name/$ver)

    echo "$i $ver $name $response"
    
    if [ $response == 404 ];
    then
        dotnet pack $i -c Release -o ./ &&
        dotnet nuget push "$name.$ver.nupkg" --api-key $2 --source $1
        
        echo "$i: pushed"        
    elif [ $response == 200 ];
    then
        echo "$i: skip"        
    else 
        echo "$i: unsupported http status code $response"
        exit 1
    fi
done

exit 0