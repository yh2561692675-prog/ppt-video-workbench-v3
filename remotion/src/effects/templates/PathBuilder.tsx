export function PathBuilder({ nodes }: { nodes: string[] }) {
  return (
    <div className="path-builder" data-direction="forward">
      {nodes.map((node, index) => (
        <div key={`${index}-${node}`} className="path-builder__node" data-node-index={index + 1}>
          {node}
        </div>
      ))}
    </div>
  );
}
