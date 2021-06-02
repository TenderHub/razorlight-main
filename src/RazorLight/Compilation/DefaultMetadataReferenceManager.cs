using System;
using System.Collections.Generic;
using Microsoft.CodeAnalysis;
using System.Reflection;
using Microsoft.Extensions.DependencyModel;
using System.Linq;
using System.IO;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using Microsoft.Extensions.Options;

namespace RazorLight.Compilation
{
	public class DefaultMetadataReferenceManager : IMetadataReferenceManager
	{
		private readonly IAssemblyDirectoryFormatter _directoryFormatter = new DefaultAssemblyDirectoryFormatter();
		public HashSet<MetadataReference> AdditionalMetadataReferences { get; }
		public HashSet<string> ExcludedAssemblies { get; }

		public DefaultMetadataReferenceManager()
		{
			AdditionalMetadataReferences = new HashSet<MetadataReference>();
			ExcludedAssemblies = new HashSet<string>();
		}

		public DefaultMetadataReferenceManager(IOptions<RazorLightOptions> options, IAssemblyDirectoryFormatter directoryFormatter) : this(options.Value.AdditionalMetadataReferences, options.Value.ExcludedAssemblies)
		{
			_directoryFormatter = directoryFormatter;
		}

		public DefaultMetadataReferenceManager(HashSet<MetadataReference> metadataReferences)
		{
			AdditionalMetadataReferences = metadataReferences ?? throw new ArgumentNullException(nameof(metadataReferences));
			ExcludedAssemblies = new HashSet<string>();
		}

		public DefaultMetadataReferenceManager(HashSet<MetadataReference> metadataReferences, HashSet<string> excludedAssemblies)
		{
			AdditionalMetadataReferences = metadataReferences ?? throw new ArgumentNullException(nameof(metadataReferences));
			ExcludedAssemblies = excludedAssemblies ?? throw new ArgumentNullException(nameof(excludedAssemblies));
		}

		public IReadOnlyList<MetadataReference> Resolve(Assembly assembly)
		{
			var dependencyContext = DependencyContext.Load(assembly);

			return Resolve(assembly, dependencyContext);
		}

		internal IReadOnlyList<MetadataReference> Resolve(Assembly assembly, DependencyContext dependencyContext)
		{
			/*
				by default this codes loads all dlls, referenced by "operation assembly" (entry assembly) 
				dependency context's compile libs are empty in a single-file app.
				to fix this, we just reference all assemblies from the current app domain 
			*/
			var metadataReferences = new List<MetadataReference>();

			unsafe
			{
				foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
				{
					if (a.TryGetRawMetadata(out byte* blob, out var length))
					{
						var moduleMetadata = ModuleMetadata.CreateFromMetadata((IntPtr) blob, length);
						var assemblyMetadata = AssemblyMetadata.Create(moduleMetadata);
						var metadataReference = assemblyMetadata.GetReference();
			
						metadataReferences.Add(metadataReference);
					}
				}
			}

			if (AdditionalMetadataReferences.Any())
			{
				metadataReferences.AddRange(AdditionalMetadataReferences);
			}

			return metadataReferences;
		}

		private static IEnumerable<Assembly> GetReferencedAssemblies(Assembly a, ISet<string> excludedAssemblies, HashSet<string> visitedAssemblies = null)
		{
			visitedAssemblies = visitedAssemblies ?? new HashSet<string>();
			if (!visitedAssemblies.Add(a.GetName().EscapedCodeBase))
			{
				yield break;
			}

			foreach (var assemblyRef in a.GetReferencedAssemblies())
			{
				if (visitedAssemblies.Contains(assemblyRef.EscapedCodeBase))
				{
					continue;
				}

				if (excludedAssemblies.Any(s => s.Contains(assemblyRef.Name)))
				{
					continue;
				}

				var loadedAssembly = Assembly.Load(assemblyRef);
				yield return loadedAssembly;
				foreach (var referenced in GetReferencedAssemblies(loadedAssembly, excludedAssemblies, visitedAssemblies))
				{
					yield return referenced;
				}
			}
		}
	}
}